"""Shared bulk format, failure handling, and credential isolation."""
import io
import json
import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'generate_test_collection')))
_LOADER_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'generate_test_collection', 'submit_to_es.py'))
submit_to_es = types.ModuleType('submit_to_es')
submit_to_es.__file__ = _LOADER_PATH
sys.modules['submit_to_es'] = submit_to_es
with open(_LOADER_PATH, encoding='utf-8') as _stream:
    exec(compile(_stream.read(), _LOADER_PATH, 'exec'), submit_to_es.__dict__)
import data_generator_common


class EsLoaderTests(unittest.TestCase):
    def test_no_arguments_hide_hyphenated_aliases(self):
        with patch('sys.stdout', io.StringIO()) as output:
            self.assertEqual(submit_to_es.main([]), 0)
        self.assertIn('--recreate_index', output.getvalue())
        self.assertIn('--data_files_dir', output.getvalue())
        self.assertIn('documents_es.ndjson', output.getvalue())
        self.assertNotIn('--recreate-index', output.getvalue())
        self.assertNotIn('--data-files-dir', output.getvalue())

    def test_index_override_is_rejected(self):
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            submit_to_es.main(['--submit', '--index', 'production'])
        self.assertEqual(error.exception.code, 2)

    def test_recreate_and_submit_are_mutually_exclusive(self):
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            submit_to_es.main(['--recreate_index', '--submit'])
        self.assertEqual(error.exception.code, 2)

    def test_recreate_does_not_require_fixture_or_submit_documents(self):
        calls = []

        def fake_request(connection, base, path, **kwargs):
            calls.append((path, kwargs.get('method', 'GET')))
            if path == '/':
                return {'version': {'number': '9.5.3'},
                        'tagline': 'You Know, for Search'}
            if kwargs.get('method') in ('DELETE', 'PUT'):
                return {'acknowledged': True}
            return {'dq_demo': {}}

        with patch('submit_to_es.connection_settings', return_value=(
                'http://localhost:9200', None, None, None)), \
                patch('submit_to_es.request', side_effect=fake_request), \
                patch('sys.stdout', io.StringIO()):
            self.assertEqual(submit_to_es.main([
                '--recreate_index', '--data_files_dir', '/missing']), 0)
        self.assertEqual(calls, [('/', 'GET'), ('/dq_demo', 'GET'),
                                 ('/dq_demo', 'DELETE'), ('/dq_demo', 'PUT')])

    def test_generated_bulk_round_trip_and_paging(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.stdout', io.StringIO()):
                data_generator_common.main(['--rows', '1000', '--seed', '42', '--data_files_dir', directory], backend='es')
            chunks = list(submit_to_es.batches(os.path.join(directory, 'documents_es.ndjson')))
            self.assertEqual([count for _, count in chunks], [500, 500])
            docs = []
            for payload, count in chunks:
                lines = payload.decode('utf-8').splitlines()
                docs.extend(json.loads(line) for line in lines[1::2])
            self.assertEqual(docs, data_generator_common.generate(1000, seed=42)[0])

    def test_cross_index_and_incomplete_pair_rejected(self):
        for value in (b'{"index":{"_id":"1","_index":"other"}}\n{"id":"1"}\n',
                      b'{"index":{"_id":"1"}}\n'):
            with tempfile.NamedTemporaryFile() as stream:
                stream.write(value)
                stream.flush()
                with self.assertRaises(submit_to_es.SubmissionError):
                    list(submit_to_es.batches(stream.name))

    def test_partial_bulk_failure_is_error(self):
        with self.assertRaises(submit_to_es.SubmissionError):
            submit_to_es.check_bulk({'errors': True, 'items': [{'index': {'status': 400, '_id': 'x'}}]}, 1)
        submit_to_es.check_bulk({'errors': False, 'items': [{'index': {'status': 201}}]}, 1)

    def test_solr_credentials_not_inherited(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini') as stream:
            stream.write('[dq]\nmain_url = http://localhost:8983/solr/my-files\nusername = solr\npassword = secret\n')
            stream.flush()
            options = SimpleNamespace(config=stream.name, main_url=None, username=None, password=None, trust_certificate=None)
            with self.assertRaisesRegex(submit_to_es.SubmissionError,
                                        'main_url identifies Solr'):
                submit_to_es.connection_settings(options)

    def test_explicit_solr_url_is_rejected(self):
        options = SimpleNamespace(config=None, main_url='http://localhost:8983/solr',
                                  username=None, password=None, trust_certificate=None)
        with patch('submit_to_es.load_config', return_value=SimpleNamespace(
                source=None, main_url=None, username=None, password=None,
                trust_certificate=None)), self.assertRaisesRegex(
                    submit_to_es.SubmissionError, 'not a Solr URL'):
            submit_to_es.connection_settings(options)

    def test_dq_target_url_override_preserves_explicit_credentials(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini') as stream:
            stream.write('[dq]\nmain_url = http://localhost:9200\nusername = es-user\npassword = es-secret\n')
            stream.flush()
            options = SimpleNamespace(config=stream.name, main_url='http://localhost:9201', username=None, password=None, trust_certificate=None)
            base, connection, _, section = submit_to_es.connection_settings(options)
            self.assertEqual(base, 'http://localhost:9201')
            self.assertEqual(section, 'DQ target settings')
            self.assertTrue(connection.authenticated)

    def test_same_submission_path_accepts_both_server_identities(self):
        identities = [
            {'version': {'number': '9.5.3'}, 'tagline': 'You Know, for Search'},
            {'version': {'number': '3.8.0', 'distribution': 'opensearch'}}]
        for identity in identities:
            with tempfile.TemporaryDirectory() as directory:
                with open(os.path.join(directory, 'documents_es.ndjson'), 'wb') as stream:
                    stream.write(b'{"index":{"_id":"1"}}\n{"id":"1"}\n')
                calls = []
                def fake_request(connection, base, path, **kwargs):
                    calls.append((path, kwargs))
                    if path == '/':
                        return identity
                    if path == '/dq_demo' and kwargs.get('method') == 'PUT':
                        return {'acknowledged': True}
                    if path == '/dq_demo':
                        return None
                    if path.endswith('/_bulk'):
                        return {'errors': False, 'items': [{'index': {'status': 201}}]}
                    if path.endswith('/_count'):
                        return {'count': 1}
                    return {}
                with patch('submit_to_es.connection_settings', return_value=('http://localhost:9201', None, None, None)), \
                        patch('submit_to_es.request', side_effect=fake_request), \
                        patch('sys.stdout', io.StringIO()):
                    self.assertEqual(submit_to_es.main(['--submit', '--data_files_dir', directory]), 0)
                self.assertEqual([path for path, _ in calls],
                                 ['/', '/dq_demo', '/dq_demo', '/dq_demo/_bulk', '/dq_demo/_refresh', '/dq_demo/_count'])

    def test_unknown_server_rejected(self):
        for identity in (None, {}, {'version': {'number': '1.0'}}, {'version': 'bad'}):
            with self.assertRaises(submit_to_es.SubmissionError):
                submit_to_es.server_identity(identity)
