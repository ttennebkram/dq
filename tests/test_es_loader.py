"""Shared bulk format, failure handling, and credential isolation."""
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'generate-test-collection')))
import es_submit
import test_data


class EsLoaderTests(unittest.TestCase):
    def test_generated_bulk_round_trip_and_paging(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.stdout', io.StringIO()):
                test_data.main(['--count', '1000', '--seed', '42', '--data_files_dir', directory], backend='es')
            chunks = list(es_submit.batches(os.path.join(directory, 'documents-es.ndjson')))
            self.assertEqual([count for _, count in chunks], [500, 500])
            docs = []
            for payload, count in chunks:
                lines = payload.decode('utf-8').splitlines()
                docs.extend(json.loads(line) for line in lines[1::2])
            self.assertEqual(docs, test_data.generate(1000, seed=42)[0])

    def test_cross_index_and_incomplete_pair_rejected(self):
        for value in (b'{"index":{"_id":"1","_index":"other"}}\n{"id":"1"}\n',
                      b'{"index":{"_id":"1"}}\n'):
            with tempfile.NamedTemporaryFile() as stream:
                stream.write(value)
                stream.flush()
                with self.assertRaises(es_submit.SubmissionError):
                    list(es_submit.batches(stream.name))

    def test_partial_bulk_failure_is_error(self):
        with self.assertRaises(es_submit.SubmissionError):
            es_submit.check_bulk({'errors': True, 'items': [{'index': {'status': 400, '_id': 'x'}}]}, 1)
        es_submit.check_bulk({'errors': False, 'items': [{'index': {'status': 201}}]}, 1)

    def test_solr_credentials_not_inherited(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini') as stream:
            stream.write('[dq]\nmain_url = http://localhost:8983/solr/my-files\nusername = solr\npassword = secret\n[opensearch]\nmain_url = http://localhost:9201\n')
            stream.flush()
            options = SimpleNamespace(config=stream.name, main_url=None, username=None, password=None, trust_certificate=None)
            base, connection, _, section = es_submit.connection_settings(options)
            self.assertEqual(base, 'http://localhost:9201')
            self.assertFalse(connection.authenticated)
            self.assertEqual(section, 'opensearch')

    def test_shared_section_url_override_preserves_explicit_credentials(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini') as stream:
            stream.write('[DEFAULT]\nusername = solr\npassword = not-for-es\n[elasticsearch]\nmain_url = http://localhost:9200\nusername = es-user\npassword = es-secret\n[opensearch]\nmain_url = http://localhost:9201\n')
            stream.flush()
            options = SimpleNamespace(config=stream.name, main_url='http://localhost:9201', username=None, password=None, trust_certificate=None)
            base, connection, _, section = es_submit.connection_settings(options)
            self.assertEqual(base, 'http://localhost:9201')
            self.assertEqual(section, 'elasticsearch')
            self.assertTrue(connection.authenticated)

    def test_same_submission_path_accepts_both_server_identities(self):
        identities = [
            {'version': {'number': '9.5.3'}, 'tagline': 'You Know, for Search'},
            {'version': {'number': '3.8.0', 'distribution': 'opensearch'}}]
        for identity in identities:
            with tempfile.TemporaryDirectory() as directory:
                with open(os.path.join(directory, 'documents-es.ndjson'), 'wb') as stream:
                    stream.write(b'{"index":{"_id":"1"}}\n{"id":"1"}\n')
                calls = []
                def fake_request(connection, base, path, **kwargs):
                    calls.append((path, kwargs))
                    if path == '/':
                        return identity
                    if path == '/dq-demo' and kwargs.get('method') == 'PUT':
                        return {'acknowledged': True}
                    if path == '/dq-demo':
                        return None
                    if path.endswith('/_bulk'):
                        return {'errors': False, 'items': [{'index': {'status': 201}}]}
                    if path.endswith('/_count'):
                        return {'count': 1}
                    return {}
                with patch('es_submit.connection_settings', return_value=('http://localhost:9201', None, None, None)), \
                        patch('es_submit.request', side_effect=fake_request), \
                        patch('sys.stdout', io.StringIO()):
                    self.assertEqual(es_submit.main(['--submit', '--data_files_dir', directory]), 0)
                self.assertEqual([path for path, _ in calls],
                                 ['/', '/dq-demo', '/dq-demo', '/dq-demo/_bulk', '/dq-demo/_refresh', '/dq-demo/_count'])

    def test_unknown_server_rejected(self):
        for identity in (None, {}, {'version': {'number': '1.0'}}, {'version': 'bad'}):
            with self.assertRaises(es_submit.SubmissionError):
                es_submit.server_identity(identity)
