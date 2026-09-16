"""Saved field filter parsing, precedence, output and persistence."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.main import main
from dq.config import load_config, write_config


class SavedFilterTests(unittest.TestCase):
    def config_file(self, directory):
        path = os.path.join(directory, 'dq.ini')
        with open(path, 'w', encoding='utf-8') as stream:
            stream.write('[dq]\nmain_url = http://solr/solr\ncollection = files\n'
                         'include_fields = file_*\n    title[ab,]_s\n'
                         'exclude_fields = *_vector\n')
        return path

    def test_lists_roundtrip_update_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.config_file(directory)
            with patch.dict(os.environ, {'DQ_COLLECTION': 'other'}):
                config = load_config(start=directory)
            self.assertEqual(config.include_fields, ['file_*', 'title[ab,]_s'])
            self.assertEqual(config.exclude_fields, ['*_vector'])
            self.assertEqual(config.collection, 'other')
            write_config(path, config.main_url, 'files', include_fields=['with space', 'x,y'])
            updated = load_config(path)
            self.assertEqual(updated.include_fields, ['with space', 'x,y'])
            self.assertEqual(updated.exclude_fields, ['*_vector'])
            with open(path) as stream:
                self.assertIn('#   file_*', stream.read())

    def test_report_uses_saved_filters_and_reports_their_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.config_file(directory)
            with patch('dq.reports.quick_checkup.report.write_report') as report, patch('sys.stdout', io.StringIO()):
                self.assertEqual(main(['--config', path, '--report', 'quick_checkup']), 0)
            self.assertEqual(report.call_args[1]['include'], ['file_*', 'title[ab,]_s'])
            self.assertEqual(report.call_args[1]['exclude'], ['*_vector'])
            details = dict((name, (value, source)) for name, value, source in report.call_args[1]['option_details'])
            self.assertIn('specified by --config', details['include_fields'][1])

    def test_cli_overrides_each_list_independently_and_can_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.config_file(directory)
            with patch('dq.main.print_fields') as output:
                main(['--config', path, '--list_fields', '--include_field', 'name_s'])
            self.assertEqual(output.call_args[1]['include'], ['name_s'])
            self.assertEqual(output.call_args[1]['exclude'], ['*_vector'])
            with patch('dq.main.print_fields') as output:
                main(['--config', path, '--list_fields', '--exclude_fields', ''])
            self.assertEqual(output.call_args[1]['exclude'], [])
            self.assertEqual(output.call_args[1]['include'], ['file_*', 'title[ab,]_s'])

    def test_cli_accepts_multiple_patterns_after_one_option(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.config_file(directory)
            with patch('dq.main.print_fields') as output:
                main(['--config', path, '--list_fields', '--include_field',
                      'abs_path_t', 'mime_type_t'])
            self.assertEqual(output.call_args[1]['include'],
                             ['abs_path_t', 'mime_type_t'])

    def test_write_config_persists_filters_and_ids_use_them(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.config_file(directory)
            with patch('sys.stdout', io.StringIO()):
                main(['--config', path, '--write_config', '--include_field', 'name_s'])
            self.assertEqual(load_config(path).include_fields, ['name_s'])
            fields = [{'name': 'name_s', 'stored': True}, {'name': 'other_s', 'stored': True}]
            with patch('dq.rules.missing_fields_base.processor.list_fields', return_value=fields), \
                 patch('dq.stored.values', return_value=iter([('one', 'name_s', False)])) as pages, \
                 patch('sys.stdout', io.StringIO()) as stdout, patch('sys.stderr', io.StringIO()):
                main(['--config', path, '--rule', 'missing_fields_base', '--action', 'csv', '--rows', '1', '--reports_dir', directory])
                self.assertIn('name_s_missing_fields_base.csv', stdout.getvalue())
                with open(os.path.join(directory, 'name_s_missing_fields_base.csv'), newline='') as stream:
                    self.assertEqual(stream.read(), 'id,reason,value\r\none,missing_fields_base: missing or null,\r\n')
                self.assertEqual(pages.call_args[0][1][0]['name'], 'name_s')
