"""Exercise config, HTTP decoding and reports on the oldest supported Python."""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from dq.cli import build_parser
from dq.config import load_config, collection_url, write_config
from dq.reports import write_empty_fields_report
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

    def test_report_tables_order_and_escaping(self):
        fields = [{'name': 'title_s', 'type': 'string', 'stored': True, 'documents': 1},
                  {'name': '_hidden_', 'type': 'string', 'stored': True, 'documents': 0}]
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'report.md')
            with patch('dq.reports.collection_document_count', return_value=2), \
                 patch('dq.reports.list_fields', return_value=fields):
                write_empty_fields_report('http://solr/c', path,
                                          option_details=[('include', 'a|b', 'command line')])
            with open(path, encoding='utf-8') as stream:
                text = stream.read()
            self.assertLess(text.index('## Summary'), text.index('## Options Used'))
            self.assertLess(text.index('## Options Used'), text.index('## Fields'))
            self.assertIn('a\\|b', text)
            self.assertIn('50.00%', text)
            self.assertNotIn('_hidden_', text)
            self.assertIn('- [Fields](#fields)', text)

    def test_exact_options_and_equals_syntax(self):
        options = build_parser().parse_args(['--main-url=http://solr/c', '-id', 'empty_fields'])
        self.assertEqual(options.main_url, 'http://solr/c')
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            build_parser().parse_args(['--incl', 'title_s'])
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
