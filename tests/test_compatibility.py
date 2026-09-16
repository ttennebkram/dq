"""Exercise config, HTTP decoding and reports on the oldest supported Python."""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from dq.main import build_parser
from dq.config import load_config, collection_url, write_config
from dq.solr import get_json, SolrError


class CompatibilityTests(unittest.TestCase):
    def test_config_write_update_and_parent_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            nested = os.path.join(directory, 'nested')
            os.mkdir(nested)
            write_config(path, 'http://localhost:8983/solr', 'old')
            write_config(path, 'http://localhost:8983/solr', 'new')
            with open(path, encoding='utf-8') as stream:
                self.assertIn('# Previous collection = old', stream.read())
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(start=nested)
            self.assertEqual(config.source, os.path.realpath(path))
            self.assertEqual(collection_url(config), 'http://localhost:8983/solr/new')
            self.assertFalse(os.path.exists(os.path.join(directory, '.dq.ini.tmp')))

    def test_section_and_explicit_config_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            with open(path, 'w', encoding='utf-8') as stream:
                stream.write('[DEFAULT]\nmain_url = http://solr/solr\n[dq]\ncollection = café\n')
            with patch.dict(os.environ, {'DQ_COLLECTION': 'wrong'}):
                config = load_config(path)
            self.assertEqual(collection_url(config), 'http://solr/solr/caf%C3%A9')

    def test_utf8_json_from_binary_response(self):
        payload = json.dumps({'text': 'café'}, ensure_ascii=False).encode('utf-8')
        with patch('dq.solr.Connection.open', return_value=io.BytesIO(payload)):
            self.assertEqual(get_json('http://solr/c', 'select'), {'text': 'café'})
        with patch('dq.solr.Connection.open', return_value=io.BytesIO(b'{broken')):
            with self.assertRaises(SolrError):
                get_json('http://solr/c', 'select')

    def test_exact_options_and_equals_syntax(self):
        options = build_parser().parse_args(['--main-url=http://solr/c', '--rule', 'missing_fields_base', '--action', 'csv'])
        self.assertEqual(options.main_url, 'http://solr/c')
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            build_parser().parse_args(['--incl', 'title_s'])
        self.assertEqual(error.exception.code, 2)

    def test_help_option_order_and_no_custom_rules_directory_option(self):
        help_text = build_parser().format_help()
        option_text = help_text[help_text.index('Configuration and Output:'):]
        ordered = ['--config FILE', '--main_url URL', '--collection NAME',
                   '--username NAME', '--password PASSWORD', '--reports_dir DIR']
        positions = [option_text.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('--processor_dir', help_text)
        self.assertIn('By default looks for dq.ini in the current directory or a parent directory.', help_text)
        self.assertIn('Rules:\n', help_text)
        self.assertIn('--list_reports', help_text)
        self.assertIn('--list_rules', help_text)
        utility_text = help_text[help_text.index('Utility Commands (choose one):'):]
        self.assertIn('--list_fields', utility_text)
        output_text = help_text[help_text.index('Output and Scanning:'):]
        self.assertLess(output_text.index('--rows N, --size N'),
                        output_text.index('--skip_null_values'))


if __name__ == '__main__':
    unittest.main()
