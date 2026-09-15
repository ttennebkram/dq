"""Limits count source documents across pages, retaining all their findings."""
import csv
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq import stored
from dq.arguments import build_parser
from dq.config import ConfigError, DqConfig, load_config, write_config
from dq.main import main
from dq.settings import resolve_rows
from dq.processors.registry import load_handler
from dq.reports.checkup import _full_workload


def page(docs, cursor):
    return {'response': {'docs': docs}, 'nextCursorMark': cursor}


class RowConfigTests(unittest.TestCase):
    def test_default_aliases_and_cli_precedence(self):
        parser = build_parser()
        self.assertEqual(resolve_rows(parser.parse_args([]), DqConfig()), -1)
        for flag in ('--rows', '--size'):
            for limit in (-1, 0, 17):
                options = parser.parse_args([flag, str(limit)])
                self.assertEqual(resolve_rows(options, DqConfig(rows=500)), limit)
        self.assertEqual(resolve_rows(parser.parse_args([]), DqConfig(rows=42)), 42)
        self.assertEqual(parser.parse_args(['--rows', '3', '--size', '7']).rows, 7)
        self.assertEqual(parser.parse_args(['--size', '3', '--rows', '0']).rows, 0)
        help_text = parser.format_help()
        self.assertIn('--rows N, --size N', help_text)
        self.assertIn('default: -1', help_text)
        self.assertIn('(no limit)', help_text)

    def test_underscore_separators_for_both_cli_names(self):
        parser = build_parser()
        for flag in ('--rows', '--size'):
            for text, expected in [('1_000', 1000), ('1_000_000', 1000000),
                                   ('+1_024', 1024), ('0_0', 0), ('1_2', 12)]:
                self.assertEqual(parser.parse_args([flag, text]).rows, expected)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://solr/c', None, rows='1_000')
            self.assertEqual(load_config(path).rows, 1000)
            with open(path) as stream:
                self.assertIn('rows = 1000', stream.read())

    def test_invalid_cli_rejected_before_network(self):
        for flag in ('--rows', '--size'):
            for value in ('-2', '1.5', 'lots', '_1000', '1000_', '1__000', '1_ 000', '1_,000', '1_0.0', '-1_0'):
                with patch('sys.stderr', io.StringIO()), patch('dq.actions.load_config') as load:
                    with self.assertRaises(SystemExit) as error:
                        main(['--report', 'full_checkup', flag, value])
                self.assertEqual(error.exception.code, 2)
                self.assertFalse(load.called)

    def test_ini_aliases_and_section_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            cases = [('[DEFAULT]\nsize=19\n', 19),
                     ('[DEFAULT]\nrows=1_000\nsize=1000\n', 1000),
                     ('[DEFAULT]\nsize=1_000_000\n', 1000000),
                     ('[DEFAULT]\nrows=0\n', 0),
                     ('[DEFAULT]\nrows=12\nsize=12\n', 12),
                     ('[DEFAULT]\nrows=-1\n[dq]\nsize=7\n', 7),
                     ('[DEFAULT]\nsize=12\n[dq]\nrows=0\n', 0)]
            for content, expected in cases:
                with open(path, 'w') as stream:
                    stream.write(content)
                self.assertEqual(load_config(path).rows, expected)
                self.assertEqual(load_config(start=directory).rows, expected)
            for content in ('rows=-2', 'size=abc', 'rows=2\nsize=3', 'rows=1__000', 'size=_1000', 'rows=1000_'):
                with open(path, 'w') as stream:
                    stream.write('[DEFAULT]\n' + content + '\n')
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_write_and_wizard_preserve_override_and_canonicalize(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            with open(path, 'w') as stream:
                stream.write('[DEFAULT]\nmain_url=http://solr/c\nsize=12\n')
            with patch('sys.stdout', io.StringIO()):
                self.assertEqual(main(['--write_config', '--config', path]), 0)
            with open(path) as stream:
                contents = stream.read()
            self.assertIn('rows = 12', contents)
            self.assertNotIn('size =', contents)
            for extra, limit in [([], 12), (['--size', '5'], 5), (['--rows', '-1'], -1)]:
                with patch('builtins.input', side_effect=[''] * 3) as prompts, patch('sys.stdout', io.StringIO()):
                    self.assertEqual(main(['--config_wizard', '--config', path] + extra), 0)
                self.assertEqual(load_config(path).rows, limit)
                self.assertFalse(any('rows' in call[0][0] or 'size' in call[0][0]
                                     for call in prompts.call_args_list))
            with open(path) as stream:
                self.assertIn('# Previous rows = 5', stream.read())
            write_config(path, 'http://solr/c', None, rows=0)
            write_config(path, 'http://solr/c', None)
            self.assertEqual(load_config(path).rows, 0)

    def test_template_parses_with_unlimited_default(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dq.ini.template')
        self.assertEqual(load_config(path).rows, -1)


class ScanLimitTests(unittest.TestCase):
    def test_counts_documents_not_values_or_fields_and_stops_without_extra_page(self):
        responses = [{'uniqueKey': 'id'}, page([
            {'dq_key': 'a', 'dq_value0': ['x', 'y'], 'dq_value1': 1},
            {'dq_key': 'b', 'dq_value0': [], 'dq_value1': None}], 'one'),
            page([{'dq_key': 'c', 'dq_value0': ['z', 'w'], 'dq_value1': 3}], 'two')]
        events = []
        with patch('dq.stored.get_json', side_effect=responses) as get:
            values = list(stored.values('url', [{'name': 'f'}, {'name': 'g'}],
                                        page_size=2, row_limit=3, include_null=True,
                                        progress=lambda phase, count: events.append((phase, count))))
        self.assertEqual(len(values), 8)
        self.assertEqual(set(row[0] for row in values), {'a', 'b', 'c'})
        self.assertEqual([call[1]['rows'] for call in get.call_args_list[1:]], [2, 1])
        self.assertEqual(events[-1], ('scanned', 3))
        self.assertEqual(get.call_count, 3)

    def test_zero_never_fetches_and_negative_limits_rejected(self):
        with patch('dq.stored.get_json') as get:
            self.assertEqual(list(stored.values('url', [{'name': 'f'}], row_limit=0)), [])
            with self.assertRaises(ValueError):
                list(stored.values('url', [{'name': 'f'}], row_limit=-2))
        self.assertFalse(get.called)

    def test_unlimited_and_short_collection_use_normal_cursor_completion(self):
        for limit in (-1, 10):
            responses = [{'uniqueKey': 'id'}, page([{'dq_key': 'a', 'dq_value0': 'x'}], 'one'),
                         page([], 'one')]
            with patch('dq.stored.get_json', side_effect=responses) as get:
                self.assertEqual(list(stored.values('url', [{'name': 'f'}], row_limit=limit)),
                                 [('a', 'f', 'x')])
            self.assertTrue(all(call[1]['rows'] > 0 for call in get.call_args_list[1:]))

    def test_rejects_partial_or_oversized_last_page(self):
        for response in [dict(page([{'dq_key': 'a'}], 'one'), responseHeader={'partialResults': True}),
                         page([{'dq_key': 'a'}, {'dq_key': 'b'}], 'one')]:
            with patch('dq.stored.get_json', side_effect=[{'uniqueKey': 'id'}, response]):
                with self.assertRaises(stored.SolrError):
                    list(stored.values('url', [{'name': 'f'}], row_limit=1))

    def test_csv_keeps_all_findings_from_last_document(self):
        responses = [{'uniqueKey': 'id'}, page([{'dq_key': 'a', 'dq_value0': [' ', '\t']}], 'one')]
        with tempfile.TemporaryDirectory() as directory, \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c', rows=100)), \
                patch('dq.processors.whitespace_only.processor.stored.fields', return_value=[{'name': 'f', 'stored': True, 'type': 'string'}]), \
                patch('dq.stored.get_json', side_effect=responses) as get, \
                patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()) as err:
            self.assertEqual(main(['--rule', 'whitespace_only', '--action', 'csv', '--size', '1', '--reports_dir', directory]), 0)
            with open(os.path.join(directory, 'f_whitespace_only.csv'), newline='') as stream:
                records = list(csv.reader(stream))
        self.assertIn('Field: f; rules: whitespace_only', out.getvalue())
        self.assertEqual(len(records), 3)
        self.assertEqual([row[0] for row in records[1:]], ['a', 'a'])
        self.assertEqual(get.call_args[1]['rows'], 1)
        self.assertIn('Maximum documents to check: 1. Each field exports at most one CSV record per failing value. If multiple rules apply to one value, the first failure in the rule chain is reported.', err.getvalue())
        self.assertIn('Documents checked: 1', out.getvalue())
        self.assertIn('Offending records exported: 2 (Number of CSV records, not counting header row)', err.getvalue())

    def test_vector_limit_checks_first_documents_without_fetching_arrays(self):
        field = {'name': 'embedding', 'stored': True, 'typeClass': 'solr.DenseVectorField'}
        responses = [{'uniqueKey': 'id'}, page([
            {'dq_key': 'a', 'dq_value0': True}, {'dq_key': 'b', 'dq_value0': False}], 'one')]
        with patch('dq.processors.missing_fields.processor.list_fields', return_value=[field]), \
                patch('dq.stored.get_json', side_effect=responses) as get, patch('sys.stderr', io.StringIO()):
            header, pages = load_handler('missing_fields', 'csv')('url', row_limit=2)
            records = [row for batch in pages for row in batch]
        self.assertEqual(records, [('b', 'missing_fields: missing or null', '')])
        self.assertEqual(get.call_args[1]['fl'], 'dq_key:id,dq_value0:exists(embedding)')
        self.assertNotIn('fq', get.call_args[1])
        # An absent presence flag is a failed response, not evidence of presence.
        with patch('dq.processors.missing_fields.processor.list_fields', return_value=[field]), \
                patch('dq.stored.get_json', side_effect=[{'uniqueKey': 'id'}, page([{'dq_key': 'a'}], 'one')]), \
                patch('sys.stderr', io.StringIO()):
            _, pages = load_handler('missing_fields', 'csv')('url', row_limit=1)
            with self.assertRaises(stored.SolrError):
                list(pages)

    def test_each_csv_processor_passes_limit_to_shared_pager(self):
        fields = [{'name': 'email_s', 'stored': True, 'type': 'string'},
                  {'name': 'date_dt', 'stored': True, 'type': 'pdate'}]
        for name in ('standard_text', 'code_points', 'email', 'ssn', 'us_phone'):
            with patch('dq.stored.fields', return_value=fields), \
                    patch('dq.stored.values', return_value=iter([])) as scan:
                _, pages = load_handler(name, 'csv')('url', row_limit=4)
                list(pages)
            self.assertEqual(scan.call_args[1]['row_limit'], 4)


class ReportLimitTests(unittest.TestCase):
    def test_summary_and_provenance_follow_effective_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, 'dq.ini'), 'w') as stream:
                stream.write('[DEFAULT]\n')
            for args, expected, source in [([], 5, 'configuration file'),
                                           (['--size', '2'], 2, 'command line'),
                                           (['--rows', '-1'], -1, 'command line')]:
                with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c', rows=5,
                                                                          source=os.path.join(directory, 'dq.ini'))), \
                        patch('dq.reports.checkup.list_fields', return_value=[{'name': 'email_s', 'type': 'string', 'stored': True}]), \
                        patch('dq.reports.checkup.collection_document_count', return_value=100), \
                        patch('dq.reports.checkup.field_document_count', return_value=90), \
                        patch('dq.stored.values', return_value=iter([])) as scan, \
                        patch('sys.stdout', io.StringIO()):
                    self.assertEqual(main(['--report', 'full_checkup', '--reports_dir', directory] + args), 0)
                self.assertEqual(scan.call_args[1]['row_limit'], expected)
                with open(os.path.join(directory, 'email_s_full_checkup.md')) as stream:
                    report = stream.read()
                self.assertIn('rows = ' + str(expected), report)
                self.assertTrue(any('rows' in line and source in line for line in report.splitlines()))

    def test_quick_presence_counts_stay_global_but_estimate_is_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'quick_checkup.md')
            with patch('dq.reports.checkup.list_fields', return_value=[{'name': 'email_s', 'type': 'string', 'stored': True}]), \
                    patch('dq.reports.checkup.collection_document_count', return_value=1000), \
                    patch('dq.reports.checkup.field_document_count', return_value=900), \
                    patch('dq.stored.values') as values:
                load_handler('quick_checkup', 'report')('url', path, row_limit=3)
            self.assertFalse(values.called)
            with open(path) as stream:
                report = stream.read()
            self.assertIn('Documents: 1,000', report)
            self.assertIn('Documents to scan: 3', report)
            self.assertIn('Presence counts cover the entire collection', report)
            self.assertIn('100', report)

    def test_full_scan_limit_and_detail_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'full_checkup.md')
            responses = [{'uniqueKey': 'id'}, page([{'dq_key': 'a', 'dq_value0': 'bad'}], 'one')]
            with patch('dq.reports.checkup.list_fields', return_value=[{'name': 'email_s', 'type': 'string', 'stored': True}]), \
                    patch('dq.reports.checkup.collection_document_count', return_value=100), \
                    patch('dq.reports.checkup.field_document_count', return_value=90), \
                    patch('dq.stored.get_json', side_effect=responses) as get, patch('sys.stdout', io.StringIO()):
                load_handler('full_checkup', 'report')('url', path, row_limit=1)
            self.assertEqual(get.call_count, 2)
            for filename in ('full_checkup.md', 'email_s_full_checkup.md'):
                with open(os.path.join(directory, filename)) as stream:
                    report = stream.read()
                self.assertIn('at most 1 documents', report)
                self.assertIn('Presence counts cover the entire collection', report)
            with open(path) as stream:
                self.assertIn('10', stream.read())

    def test_deferred_date_report_does_not_scan(self):
        from dq.processors import ReportError
        with patch('dq.stored.values') as scan, self.assertRaises(ReportError):
            load_handler('date_checker', 'report')('url', 'date_checker.md', row_limit=3)
        self.assertFalse(scan.called)
