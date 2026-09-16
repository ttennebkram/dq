"""Per-field routing, filenames, shared scans, and final relative file lists."""
import csv
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.config import DqConfig
from dq.files import field_filename, display_path
from dq.main import main
from dq.progress import ScanProgress


FIELDS = [{'name': name, 'type': 'string', 'stored': True}
          for name in ('Email_t', 'notes-t', 'clean_t')]


class FieldOutputTests(unittest.TestCase):
    def test_filename_sanitizes_each_character_preserving_case(self):
        self.assertEqual(field_filename('Ab09-_/x.\u00e9 !', 'email', 'csv'), 'Ab09-__x_____email.csv')
        self.assertEqual(field_filename('../outside', 'email', 'md'), '___outside_email.md')
        with patch('dq.files.os.path.relpath', side_effect=ValueError):
            self.assertEqual(display_path('/different-drive/file.md'), os.path.abspath('/different-drive/file.md'))

    def test_progress_names_field_before_processor(self):
        out = io.StringIO()
        ScanProgress('standard_text_composite', stream=out).start(['abs_path_t'])
        self.assertTrue(out.getvalue().startswith('Field: abs_path_t; rules: standard_text_composite\n'))

    def test_csv_one_pass_routes_multivalues_and_keeps_empty_files(self):
        response = {'response': {'docs': [
            {'dq_key': '001', 'dq_value0': None, 'dq_value1': [' ', ''], 'dq_value2': 'clean'},
            {'dq_key': '002', 'dq_value0': ' \ufffd ', 'dq_value1': 'plain', 'dq_value2': 'clean'}]},
            'nextCursorMark': 'next'}
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.stored.list_fields', return_value=FIELDS), \
                patch('dq.stored.get_json', side_effect=[{'uniqueKey': 'id'}, response]) as fetch, \
                patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()) as err:
            self.assertEqual(main(['--rule', 'standard_text_composite', '--action', 'csv', '--include_fields', '*t', '--rows', '2']), 0)
            self.assertEqual(fetch.call_count, 2)  # One schema lookup and one shared data page.
            self.assertIn('dq_value0:Email_t,dq_value1:notes-t,dq_value2:clean_t', fetch.call_args[1]['fl'])
            files = sorted(os.listdir(os.path.join(root, 'reports')))
            self.assertEqual(files, ['Email_t_standard_text_composite.csv', 'clean_t_standard_text_composite.csv', 'notes-t_standard_text_composite.csv', 'processing-stats.jsonl'])
            def rows(name):
                with open(os.path.join(root, 'reports', name + '_standard_text_composite.csv'), encoding='utf-8', newline='') as stream:
                    return list(csv.reader(stream))
            email = rows('Email_t')
            self.assertEqual(len(email), 3)  # Header, null, first failure (surrounding whitespace).
            self.assertEqual(email[1], ['001', 'missing_fields_base: missing or null', ''])
            self.assertTrue(all(len(row) == 3 for row in email))
            self.assertEqual([row[2] for row in rows('notes-t')[1:]], [' ', ''])
            self.assertEqual(rows('clean_t'), [['id', 'reason', 'value']])
            listed = out.getvalue().split('Files created:\n')[1].splitlines()
            expected_counts = {'Email_t': 2, 'notes-t': 2, 'clean_t': 0}
            expected = ['  reports/{0}_standard_text_composite.csv ({1} data records; header not counted)'.format(
                        f['name'], expected_counts[f['name']]) for f in FIELDS]
            self.assertEqual(listed, expected + ['  reports/processing-stats.jsonl'])
            self.assertNotIn(root, out.getvalue())
            self.assertIn('Documents checked: 2', out.getvalue())
            self.assertIn('Offending records exported by field:', err.getvalue())
            self.assertIn('  Email_t: 2', err.getvalue())
            self.assertIn('  notes-t: 2', err.getvalue())
            self.assertIn('  clean_t: 0', err.getvalue())
            self.assertIn('Total offending records exported across all fields: 4', err.getvalue())

    def test_summary_includes_multiple_special_reports(self):
        def custom_report(target, path, **options):
            with open(path, 'w') as stream:
                stream.write('custom report')
            return [path]
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.actions.load_handler', return_value=custom_report), patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main(['--reports', 'quick_checkup', 'date_checker']), 0)
            self.assertEqual(out.getvalue().split('Main Report Files:\n')[1].splitlines(),
                             ['  reports/quick_checkup.md', '  reports/date_checker.md'])

    def test_sanitized_collisions_do_not_scan_or_overwrite_csv(self):
        for names in [('a/b', 'a?b'), ('Name', 'name')]:
            with tempfile.TemporaryDirectory() as root:
                destination = os.path.join(root, 'reports')
                os.mkdir(destination)
                path = os.path.join(destination, field_filename(names[0], 'standard_text_composite', 'csv'))
                with open(path, 'w') as stream:
                    stream.write('previous output')
                with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                        patch('dq.stored.fields', return_value=[{'name': n, 'type': 'string'} for n in names]), \
                        patch('dq.stored.values') as scan, patch('sys.stderr', io.StringIO()) as err, \
                        self.assertRaises(SystemExit) as result:
                    main(['--rule', 'standard_text_composite', '--action', 'csv', '--reports_dir', destination])
                self.assertEqual(result.exception.code, 2)
                self.assertFalse(scan.called)
                self.assertIn('filenames collide', err.getvalue())
                with open(path) as stream:
                    self.assertEqual(stream.read(), 'previous output')

    def test_missing_fields_base_multi_field_scan_and_three_columns(self):
        fields = [{'name': 'a', 'stored': True}, {'name': 'b', 'stored': True}]
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.rules.missing_fields_base.processor.list_fields', return_value=fields), \
                patch('dq.stored.values', return_value=iter([('1', 'a', False), ('1', 'b', False), ('2', 'a', True)])) as scan, \
                patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()):
            self.assertEqual(main(['--rule', 'missing_fields_base', '--action', 'csv', '--skip_null_values', '--rows', '2']), 0)
            self.assertEqual(scan.call_count, 1)
            self.assertEqual(scan.call_args[0][1], fields)
            for name in ('a', 'b'):
                with open(os.path.join(root, 'reports', name + '_missing_fields_base.csv'), newline='') as stream:
                    rows = list(csv.reader(stream))
                self.assertEqual(rows[0], ['id', 'reason', 'value'])
                self.assertEqual([row[2] for row in rows[1:]], [''])
                self.assertTrue(all(len(row) == 3 for row in rows))

    def test_checkup_final_list_contains_overview_and_every_field(self):
        for action in ('quick_checkup', 'full_checkup'):
            with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                    patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.reports.checkup.list_fields', return_value=FIELDS), \
                    patch('dq.reports.checkup.collection_document_count', return_value=10), \
                    patch('dq.reports.checkup.field_document_count', return_value=9), \
                    patch('dq.stored.values', return_value=iter([])) as scan, \
                    patch('sys.stdout', io.StringIO()) as out:
                self.assertEqual(main(['--report', action]), 0)
                self.assertEqual(scan.call_count, 0 if action == 'quick_checkup' else 1)
                paths = ['reports/' + action + '.md']
                expected = '  ' + paths[0] + '\n'
                if action == 'full_checkup':
                    paths += ['reports/' + f['name'] + '_' + action + '.md' for f in FIELDS]
                    paths += ['reports/' + f['name'] + '_full_checkup.csv' for f in FIELDS]
                    expected += '\nOther Created Files:\n' + ''.join('  ' + p + '\n' for p in paths[1:])
                self.assertEqual(out.getvalue().split('Main Report File:\n')[1], expected)
                self.assertEqual(sorted(os.listdir(os.path.join(root, 'reports'))),
                                 sorted(os.path.basename(p) for p in paths))
                with open(os.path.join(root, paths[0])) as stream:
                    overview = stream.read()
                for relative in paths[1:]:
                    self.assertTrue(os.path.isfile(os.path.join(root, relative)))
                    self.assertIn('(' + os.path.basename(relative) + ')', overview)

    def test_report_without_overview_separates_images(self):
        def report(target, path, **options):
            directory = os.path.dirname(path)
            paths = [os.path.join(directory, 'created_dt_date_checker.md'),
                     os.path.join(directory, 'created_dt_date_checker_dates.svg')]
            for filename in paths:
                with open(filename, 'w') as stream:
                    stream.write('artifact')
            return paths
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.actions.load_handler', return_value=report), patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main(['--report', 'date_checker']), 0)
            self.assertEqual(out.getvalue().split('Main Report File:\n')[1],
                             '  reports/created_dt_date_checker.md\n\nOther Created Files:\n  reports/created_dt_date_checker_dates.svg\n')

    def test_legacy_report_without_return_value_is_main(self):
        def report(target, path, **options):
            with open(path, 'w') as stream:
                stream.write('report')
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.actions.load_handler', return_value=report), patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main(['--report', 'sample']), 0)
            self.assertEqual(out.getvalue().split('Main Report File:\n')[1], '  reports/sample.md\n')
