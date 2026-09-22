"""Demo reloads are nondestructive unless recreation is explicit."""
import os
import io
import tempfile
import runpy
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

loader = runpy.run_path(os.path.join(os.path.dirname(__file__), '..', 'generate_test_collection', 'submit_to_solr.py'))
prepare = loader['prepare_collection']
solr_base = loader['solr_base']
validate_dynamic_fields = loader['validate_dynamic_fields']


class DemoLoaderTests(unittest.TestCase):
    def test_required_dynamic_fields_are_validated(self):
        response = {'dynamicFields': [
            {'name': '*_t', 'type': 'text_general'},
            {'name': '*_s', 'type': 'string'},
            {'name': '*_dt', 'type': 'pdate'}]}
        with patch.dict(validate_dynamic_fields.__globals__,
                        get_json=Mock(return_value=response)):
            self.assertIsNone(validate_dynamic_fields('url', None))
        response['dynamicFields'][0]['type'] = 'string'
        with patch.dict(validate_dynamic_fields.__globals__,
                        get_json=Mock(return_value=response)), \
                self.assertRaisesRegex(ValueError, r'\*_t -> text_general'):
            validate_dynamic_fields('url', None)

    def test_elasticsearch_url_is_rejected(self):
        config = type('Config', (), {'main_url': 'http://localhost:9200'})()
        with self.assertRaisesRegex(ValueError, 'must identify Solr'):
            solr_base(config)

    def test_configured_collection_is_ignored(self):
        config = type('Config', (), {
            'main_url': 'http://localhost:8983/solr',
            'collection': 'production'})()
        self.assertEqual(solr_base(config), 'http://localhost:8983/solr')

        config.main_url = 'http://localhost:8983/solr/production'
        config.collection = None
        self.assertEqual(solr_base(config), 'http://localhost:8983/solr')

    def test_existing_collection_is_not_modified(self):
        get = Mock(side_effect=[{'collections':['dq_demo']}])
        with patch.dict(prepare.__globals__, get_json=get):
            self.assertFalse(prepare('url', None))
        self.assertEqual([c[1]['action'] for c in get.call_args_list], ['LIST'])

    def test_recreate_deletes_then_creates_only_demo(self):
        get = Mock(side_effect=[{'collections':['dq_demo','my-files']}, {'configSets':['dq_demo']},
            {'cluster':{'collections':{'dq_demo':{'configName':'dq_demo'}, 'my-files':{'configName':'other'}}}}, {}, {}, {}])
        with patch.dict(prepare.__globals__, get_json=get):
            self.assertTrue(prepare('url', None, True))
        calls = get.call_args_list[3:]
        self.assertEqual([c[1]['action'] for c in calls], ['DELETE','DELETE','CREATE'])
        self.assertTrue(all(c[1]['name']=='dq_demo' for c in calls))
        self.assertNotIn('collection.configName', calls[-1][1])

    def test_shared_configset_refused_before_delete(self):
        get = Mock(side_effect=[{'collections':['dq_demo']}, {'configSets':['dq_demo']},
            {'cluster':{'collections':{'other':{'configName':'dq_demo'}}}}])
        with patch.dict(prepare.__globals__, get_json=get):
            with self.assertRaises(ValueError):
                prepare('url', None, True)
        self.assertFalse(any(c[1]['action']=='DELETE' for c in get.call_args_list))

    def test_missing_collection_created(self):
        get = Mock(side_effect=[{'collections':['my-files']}, {'configSets':['_default']},
            {'cluster':{'collections':{'my-files':{'configName':'other'}}}}, {}])
        with patch.dict(prepare.__globals__, get_json=get):
            self.assertTrue(prepare('url', None))
        self.assertEqual([c[1]['action'] for c in get.call_args_list], ['LIST','LIST','CLUSTERSTATUS','CREATE'])
        self.assertNotIn('collection.configName', get.call_args_list[-1][1])


    def test_no_arguments_only_show_usage(self):
        main = loader['main']
        with patch('sys.stdout', io.StringIO()) as output, \
             patch.dict(main.__globals__, load_config=Mock(side_effect=AssertionError('no config access'))), \
             patch.dict(main.__globals__, describe_data_file=Mock()):
            self.assertEqual(main([]), 0)
        self.assertIn('--submit', output.getvalue())
        self.assertIn('documents_solr.json', output.getvalue())
        self.assertIn('--recreate_collection', output.getvalue())
        self.assertIn('--recreate_index', output.getvalue())
        self.assertNotIn('--recreate-collection', output.getvalue())
        self.assertNotIn('--preserve-empty-strings', output.getvalue())
        self.assertNotIn('--data-files-dir', output.getvalue())

    def test_directory_alone_is_not_an_action(self):
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            loader['main'](['--data_files_dir', '.'])
        self.assertEqual(error.exception.code, 2)

    def test_recreate_and_submit_are_mutually_exclusive(self):
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            loader['main'](['--recreate_collection', '--submit'])
        self.assertEqual(error.exception.code, 2)

    def test_recreate_does_not_require_fixture_or_submit_documents(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *unused):
                return False

            def read(self):
                return b'{}'

        connection = Mock()
        connection.open.return_value = Response()
        config = SimpleNamespace(main_url='http://localhost:8983/solr', collection=None,
                                 trust_certificate=None, source=None,
                                 username=None, password=None)
        cluster = {'cluster': {'collections': {
            'dq_demo': {'configName': 'dq_demo'}}}}
        with patch.dict(loader['main'].__globals__,
                        load_config=Mock(return_value=config),
                        Connection=Mock(return_value=connection),
                        prepare_collection=Mock(return_value=True),
                        validate_dynamic_fields=Mock(),
                        get_json=Mock(return_value=cluster)), \
                patch('sys.stdout', io.StringIO()):
            self.assertEqual(loader['main']([
                '--recreate_index', '--data_files_dir', '/missing']), 0)
        urls = [call[0][0].full_url for call in connection.open.call_args_list]
        self.assertFalse(any(url.endswith('/schema') for url in urls))
        self.assertTrue(any(url.endswith('/config') for url in urls))
        self.assertFalse(any('/update' in url for url in urls))


    def test_file_status_existing_and_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.stdout', io.StringIO()) as output:
                loader['describe_data_file'](directory)
            self.assertIn(os.path.join(directory, 'documents_solr.json'), output.getvalue())
            self.assertIn('Exists: no', output.getvalue())
            with open(os.path.join(directory, 'documents_solr.json'), 'w') as stream:
                stream.write('[]')
            with patch('sys.stdout', io.StringIO()) as output:
                loader['describe_data_file'](directory)
            self.assertIn('Exists: yes', output.getvalue())
            self.assertIn('Size: 1 lines, 2 bytes', output.getvalue())
            self.assertIn('Last modified:', output.getvalue())
            self.assertIn('Readable: yes', output.getvalue())
