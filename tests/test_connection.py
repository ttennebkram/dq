"""Credential handling, configuration and transport regression tests."""

import io
import os
import stat
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request
from unittest.mock import patch
from dq.cli import build_parser, _report_option_details
from dq.config import DqConfig, ConfigError, collection_url, load_config, write_config
from dq.connection import Connection, NoRedirect, SameSchemeRedirect, connection_values


class ConnectionTests(unittest.TestCase):
    def test_credentials_literal_and_private_without_old_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'https://solr/solr', 'files', username='mark', password='old%secret')
            write_config(path, 'https://solr/solr', 'files', password='new%secret')
            config = load_config(path)
            self.assertEqual(config.password, 'new%secret')
            self.assertEqual(config.username, 'mark')
            with open(path) as stream:
                self.assertNotIn('old%secret', stream.read())
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_relative_certificate_paths_and_overrides(self):
        config = DqConfig(source='/tmp/project/dq.ini', trust_certificate='certs/ca.pem',
                          username='mark', password='secret')
        parser = build_parser()
        values = connection_values(parser.parse_args([]), config)
        self.assertEqual(values['trust_certificate'], os.path.realpath('/tmp/project/certs/ca.pem'))
        values = connection_values(parser.parse_args(['--trust_certificate', 'other.pem']), config)
        self.assertEqual(values['trust_certificate'], os.path.realpath('other.pem'))

    def test_password_redacted_in_options(self):
        config = DqConfig(main_url='https://solr/solr', collection='files',
                          username='mark', password='secret')
        options = build_parser().parse_args(['--report', 'empty_fields'])
        options.report = ['empty_fields']
        details = _report_option_details(options, config, 'https://solr/solr/files', 'out.md')
        self.assertNotIn('secret', repr(details))
        self.assertIn('[redacted]', repr(details))

    def test_redirect_refused_and_auth_header_not_redirectable(self):
        connection = Connection(username='mark', password='secret')
        request = Request('https://solr/solr/files')
        with patch.object(connection.opener, 'open', return_value=io.BytesIO(b'{}')):
            connection.open(request)
        self.assertIn('Authorization', request.unredirected_hdrs)
        self.assertNotIn('Authorization', request.headers)
        with self.assertRaises(HTTPError):
            NoRedirect().redirect_request(request, io.BytesIO(), 302, 'Found', {}, 'https://elsewhere/')

    def test_pair_required_and_url_credentials_rejected(self):
        with self.assertRaises(ConfigError):
            Connection(username='mark')
        with self.assertRaises(ConfigError) as error:
            collection_url(DqConfig(main_url='https://mark:secret@solr/files'))
        self.assertNotIn('secret', str(error.exception))

    def test_cross_scheme_redirects_refused_in_both_directions(self):
        for original, destination in [('http', 'https'), ('https', 'http')]:
            for status in (301, 302, 303, 307):
                request = Request(original + '://solr/solr/files')
                with self.assertRaises(URLError) as error:
                    SameSchemeRedirect().redirect_request(
                        request, io.BytesIO(), status, 'Redirect', {},
                        destination + '://solr/solr/files')
                self.assertIn('will not switch from ' + original + ' to ' + destination,
                              str(error.exception))

    def test_same_scheme_redirects_still_allowed_without_auth(self):
        for scheme in ('http', 'https'):
            destination = scheme + '://solr/solr/files/'
            request = SameSchemeRedirect().redirect_request(
                Request(scheme + '://solr/solr/files'), io.BytesIO(), 302,
                'Found', {}, destination)
            self.assertEqual(request.full_url, destination)

    def test_default_requests_use_scheme_protection(self):
        from dq.solr import get_json, SolrError
        connection = Connection()
        self.assertTrue(any(isinstance(handler, SameSchemeRedirect)
                            for handler in connection.opener.handlers))
        with patch('dq.solr.Connection', return_value=connection), \
             patch.object(connection, 'open', side_effect=URLError(
                 'redirect refused: DQ will not switch from http to https')):
            with self.assertRaises(SolrError) as error:
                get_json('http://solr/solr/files', 'select')
        self.assertIn('will not switch from http to https', str(error.exception))

    def test_no_config_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'HOME': directory}, clear=True):
                self.assertIsNone(load_config(start=directory).source)


if __name__ == '__main__':
    unittest.main()
