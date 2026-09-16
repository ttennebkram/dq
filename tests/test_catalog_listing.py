"""Rule and report catalogs are target-free stdout commands."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from dq.config import DqConfig, catalog_url
from dq.main import main
from dq import elasticsearch, solr


class CatalogListingTests(unittest.TestCase):
    def run_catalog(self, option):
        with patch('dq.main.load_config') as load, patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main([option]), 0)
        self.assertFalse(load.called)
        return out.getvalue()

    def test_list_reports_includes_status(self):
        output = self.run_catalog('--list_reports')
        self.assertIn('REPORT', output)
        self.assertIn('STATUS', output)
        self.assertRegex(output, r'(?m)^quick_checkup\s+Implemented\s+')
        self.assertNotIn('term_stats', output)
        self.assertNotIn('date_checker', output)

    def test_list_rules_includes_base_and_composite_types(self):
        output = self.run_catalog('--list_rules')
        self.assertIn('RULE', output)
        self.assertIn('TYPE', output)
        self.assertRegex(output, r'(?m)^email_base\s+Base\s+')
        self.assertRegex(output, r'(?m)^email_composite\s+Predefined Composite\s+')

    def test_hyphenated_aliases_remain_accepted(self):
        self.assertIn('Reports:', self.run_catalog('--list-reports'))
        self.assertIn('Rules:', self.run_catalog('--list-rules'))

    def test_catalog_url_removes_solr_collection_or_search_index(self):
        self.assertEqual(
            catalog_url(DqConfig(main_url='http://localhost:8983/solr/my-files')),
            'http://localhost:8983/solr')
        self.assertEqual(
            catalog_url(DqConfig(main_url='https://host.example/proxy/solr/my-files')),
            'https://host.example/proxy/solr')
        self.assertEqual(
            catalog_url(DqConfig(main_url='http://localhost:9200/dq-demo')),
            'http://localhost:9200')

    def test_engine_catalog_clients_sort_names(self):
        with patch('dq.solr.get_json', return_value={'collections': ['zeta', 'alpha']}) as request:
            self.assertEqual(solr.list_collections('http://host/solr'), ['alpha', 'zeta'])
        self.assertEqual(request.call_args[0], ('http://host/solr', 'admin/collections'))
        self.assertEqual(request.call_args[1]['action'], 'LIST')
        with patch('dq.elasticsearch.request_json', return_value=[
                {'index': 'zeta'}, {'index': 'alpha'}]) as request:
            self.assertEqual(elasticsearch.list_indexes('http://host:9200'), ['alpha', 'zeta'])
        self.assertEqual(request.call_args[0], ('http://host:9200', '_cat/indices'))
        self.assertEqual(request.call_args[1]['format'], 'json')

    def test_list_collection_and_index_commands_use_server_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            with open(path, 'w') as stream:
                stream.write('[dq]\nmain_url = http://localhost:8983/solr/my-files\n')
            for option, noun in (('--list_collections', 'Collections'),
                                 ('--list_indexes', 'Indexes')):
                with self.subTest(option=option), \
                        patch('dq.listing.list_collections', return_value=['alpha', 'my-files']) as listing, \
                        patch('sys.stdout', io.StringIO()) as out:
                    self.assertEqual(main(['--config', path, option]), 0)
                self.assertEqual(listing.call_args[0][0], 'http://localhost:8983/solr')
                self.assertIn(noun + ': 2', out.getvalue())

    def test_catalog_is_exclusive_with_other_actions(self):
        for arguments in (['--list_rules', '--report', 'quick_checkup'],
                          ['--list_reports', '--list_fields'],
                          ['--list_collections', '--list_indexes'],
                          ['--list_rules', '--list_reports']):
            with self.subTest(arguments=arguments), patch('sys.stderr', io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                main(arguments)
            self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
