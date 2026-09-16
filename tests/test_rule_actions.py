"""Focused coverage for explicit rules/actions and special-report artifacts."""
import csv
import fnmatch
import io
import os
import re
import shlex
import tempfile
import unittest
from unittest.mock import patch
from dq.arguments import build_parser, resolve_selection
from dq.config import DqConfig
from dq.main import main
from dq.registry import report_names, csv_names


class RuleActionTests(unittest.TestCase):
    def selection(self, args):
        parser = build_parser()
        options = parser.parse_args(args)
        resolve_selection(options, parser)
        return options

    def test_explicit_rule_and_action_selection(self):
        for args in (['--rule', 'email_composite', '--action', 'csv'],
                     ['--rules', 'email_composite', '--action', 'csv']):
            options = self.selection(args)
            self.assertEqual(options.rule, ['email_composite'])
            self.assertEqual(options.action, 'csv')
        options = self.selection(['--rule', 'email_composite'])
        self.assertEqual(options.rule, ['email_composite'])
        self.assertEqual(options.action, 'csv')
        self.assertEqual(options.action_source, 'default for --rule/--rules')
        options = self.selection(['--rules', 'standard_text_composite', 'email_composite', '--action', 'csv'])
        self.assertEqual(options.rule, ['standard_text_composite', 'email_composite'])
        for args, expected in ((['--report', 'quick_checkup'], ['quick_checkup']),
                               (['--action', 'report', '--reports', 'quick_checkup'], ['quick_checkup']),
                               (['--report', 'quick_checkup', 'full_checkup'], ['quick_checkup', 'full_checkup']),
                               (['--reports', 'quick_checkup', 'full_checkup'], ['quick_checkup', 'full_checkup'])):
            options = self.selection(args)
            self.assertEqual(options.report, expected)
            self.assertEqual(options.rule, [])
            self.assertEqual(options.action, 'report')

    def test_invalid_combinations_before_loading_configuration(self):
        cases = [['--rule', 'email_composite', '--action', 'report'],
                 ['--rule', 'email_composite', '--report', 'quick_checkup'],
                 ['--report', 'quick_checkup', '--action', 'csv'],
                 ['--rule', 'email_composite', '--action', 'csv', '--list_fields'],
                 ['--action', 'modify']]
        for args in cases:
            with patch('dq.main.load_config') as load, patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(load.called)

    def test_missing_selection_names_the_missing_piece_after_target(self):
        for args, message in [(['--action', 'csv'], 'no rule was selected'),
                              (['--action', 'report'], 'no report was selected')]:
            with patch('dq.main.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('sys.stderr', io.StringIO()) as err, self.assertRaises(SystemExit):
                main(args)
            self.assertIn('target resolves to http://solr/c', err.getvalue())
            self.assertIn(message, err.getvalue())

    def test_ordinary_rules_have_no_generic_markdown(self):
        for rule in ('standard_text_composite', 'code_points_base', 'email_composite', 'ssn_composite', 'us_phone_composite'):
            self.assertIn(rule, csv_names())
            self.assertNotIn(rule, report_names())
            with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.stored.values') as scan, patch('sys.stderr', io.StringIO()) as err, self.assertRaises(SystemExit):
                main(['--report', rule])
            self.assertFalse(scan.called)
            self.assertIn('is a rule; use --rule', err.getvalue())

    def test_rule_dispatch_writes_csv(self):
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.stored.fields', return_value=[{'name': 'email_t', 'type': 'string', 'stored': True}]), \
                patch('dq.stored.values', return_value=iter([('1', 'email_t', 'bad')])), \
                patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()):
            self.assertEqual(main(['--rule', 'email_composite', '--action', 'csv']), 0)
            self.assertIn('  reports/email_t_email_composite.csv', out.getvalue())
            self.assertEqual(os.listdir(os.path.join(root, 'reports')), ['email_t_email_composite.csv'])

    def test_multiple_rules_share_scan_and_export_first_failure(self):
        source = [('1', 'email_t', ' bad@example.com'),
                  ('2', 'email_t', 'bad'),
                  ('3', 'email_t', 'good@example.com')]
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.stored.fields', return_value=[{'name': 'email_t', 'type': 'string', 'stored': True}]), \
                patch('dq.stored.values', return_value=iter(source)) as scan, \
                patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()):
            self.assertEqual(main(['--rules', 'standard_text_composite', 'email_composite', '--action', 'csv']), 0)
            self.assertEqual(scan.call_count, 1)
            path = os.path.join(root, 'reports', 'email_t_standard_text_composite_email_composite.csv')
            with open(path, newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual([row[0] for row in rows[1:]], ['1', '2'])
            self.assertTrue(rows[1][1].startswith('surrounding_whitespace_base:'))
            self.assertTrue(rows[2][1].startswith('email_base:'))
            self.assertIn('reports/email_t_standard_text_composite_email_composite.csv', out.getvalue())


class SpecialReportTests(unittest.TestCase):
    def test_full_report_counts_csv_links_and_one_scan(self):
        fields = [{'name': name, 'stored': True, 'type': 'string'} for name in ('email_t', 'notes_t', 'clean_t')]
        fields.append({'name': 'vector', 'stored': True, 'typeClass': 'solr.DenseVectorField'})
        long_id, long_value = 'i' * 600, 'v' * 700
        source = [(long_id, 'email_t', long_value), ('2', 'notes_t', ''), ('2', 'clean_t', 'fine')]
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.reports.checkup.list_fields', return_value=fields), \
                patch('dq.reports.checkup.collection_document_count', return_value=2), \
                patch('dq.reports.checkup.field_document_count', return_value=1), \
                patch('dq.stored.values', return_value=iter(source)) as scan, patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main(['--report', 'full_checkup', '--action', 'report']), 0)
            self.assertEqual(scan.call_count, 1)
            self.assertEqual([f['name'] for f in scan.call_args[0][1]], ['email_t', 'notes_t', 'clean_t'])
            with open(os.path.join(root, 'reports', 'full_checkup.md')) as stream:
                report = stream.read()
            self.assertIn('Docs w/Value', report)
            self.assertLess(report.index('Docs w/Value'), report.index('Docs w/o Value'))
            self.assertRegex(report, r'`email_t`\s*\|\s*1\s*\|\s*1\s*\|')
            self.assertIn('(email_t_full_checkup.md)', report)
            self.assertIn('(email_t_full_checkup.csv)', report)
            self.assertIn('presence counts only', report)
            with open(os.path.join(root, 'reports', 'email_t_full_checkup.csv'), newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows[0], ['id', 'reason', 'value'])
            self.assertEqual(rows[1][0], long_id)
            self.assertEqual(rows[1][2], long_value)
            self.assertTrue(rows[1][1].startswith('email_base: no configured regex matched'))
            with open(os.path.join(root, 'reports', 'clean_t_full_checkup.csv'), newline='') as stream:
                self.assertEqual(list(csv.reader(stream)), [['id', 'reason', 'value']])
            self.assertFalse(os.path.exists(os.path.join(root, 'reports', 'vector_full_checkup.csv')))
            with open(os.path.join(root, 'reports', 'email_t_full_checkup.md')) as stream:
                self.assertIn('(email_t_full_checkup.csv)', stream.read())
            summary = out.getvalue().split('Main Report File:\n')[1]
            main_output, others = summary.split('\nOther Created Files:\n')
            self.assertEqual(main_output, '  reports/full_checkup.md\n')
            self.assertEqual(len(others.splitlines()), 7)
            for item in others.splitlines():
                self.assertTrue(item.strip().startswith('reports/'))
                self.assertTrue(os.path.isfile(os.path.join(root, item.strip())))

    def test_quick_followups_are_at_bottom_use_exact_fields_and_do_not_scan(self):
        field = "email ' [x]*_t"
        with tempfile.TemporaryDirectory() as root:
            config = os.path.join(root, 'settings file.ini')
            with open(config, 'w') as stream:
                stream.write('[DEFAULT]\nmain_url=http://solr/c\n')
            with patch('os.getcwd', return_value=root), \
                    patch('dq.reports.checkup.list_fields', return_value=[{'name': field, 'type': 'string', 'stored': True}]), \
                    patch('dq.reports.checkup.collection_document_count', return_value=10), \
                    patch('dq.reports.checkup.field_document_count', return_value=9), \
                    patch('dq.stored.values') as scan, patch('sys.stdout', io.StringIO()):
                self.assertEqual(main(['--report', 'quick_checkup', '--config', config]), 0)
            self.assertFalse(scan.called)
            with open(os.path.join(root, 'reports', 'quick_checkup.md')) as stream:
                report = stream.read()
            self.assertLess(report.index('## Run Additional Checks'), report.index('## Full Report Workload Estimate'))
            commands = re.findall(r'```sh\n([^\n]+)\n```', report.split('## Run Additional Checks')[1])
            self.assertEqual(len(commands), 2)
            for command in commands:
                options = build_parser().parse_args(shlex.split(command)[1:])
                resolve_selection(options, build_parser())
                self.assertIsNone(options.main_url)
                self.assertEqual(options.config, 'settings file.ini')
                self.assertEqual(options.exclude_fields, [''])
                self.assertEqual(options.rows, 1000)
                self.assertTrue(fnmatch.fnmatchcase(field, options.include_fields[0]))
                self.assertFalse(fnmatch.fnmatchcase('email anything_t', options.include_fields[0]))

    def test_full_csv_flushes_all_findings_and_respects_skip_null(self):
        source = [('null', 'notes_t', None)] + [(str(i), 'notes_t', '') for i in range(1002)]
        with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.reports.checkup.list_fields', return_value=[{'name': 'notes_t', 'type': 'string', 'stored': True}]), \
                patch('dq.reports.checkup.collection_document_count', return_value=1003), \
                patch('dq.reports.checkup.field_document_count', return_value=1002), \
                patch('dq.stored.values', return_value=iter(source)), patch('sys.stdout', io.StringIO()):
            self.assertEqual(main(['--report', 'full_checkup', '--skip_null_values']), 0)
            with open(os.path.join(root, 'reports', 'notes_t_full_checkup.csv'), newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows), 1003)
            self.assertEqual(rows[-1][0], '1001')
            self.assertTrue(all(row[1] == 'empty_strings_base: empty string' for row in rows[1:]))
            with open(os.path.join(root, 'reports', 'notes_t_full_checkup.md')) as stream:
                report = stream.read()
            self.assertIn('Finding rows: 1,002', report)
            self.assertEqual(report.count('empty_strings_base: empty string'), 100)
            self.assertNotIn('missing_fields_base: missing or null', report)
            self.assertIn('Non-null stored values scanned: 1,002', report)
            self.assertIn('CSV records: 1,002', report)


class ReportLinkTests(unittest.TestCase):
    def test_source_links_preserve_https_and_escape_field_names(self):
        from urllib.parse import parse_qs, urlsplit
        from dq.reports.links import solr_query_url
        field = {'name': 'a+b:field'}
        url = solr_query_url('https://solr.example/solr/demo', field, missing=True)
        self.assertEqual(urlsplit(url).scheme, 'https')
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query['rows'], ['10'])
        self.assertEqual(query['dq_field'], [field['name']])
        self.assertEqual(query['fq'], [r'{!lucene}(*:* AND -a\+b\:field:*)'])
        vector = {'name': 'v', 'typeClass': 'solr.DenseVectorField'}
        query = parse_qs(urlsplit(solr_query_url('http://solr/c', vector, missing=True)).query)
        self.assertEqual(query['fq'], ['{!frange l=0 u=0}exists($dq_field)'])

    def test_date_report_embeds_and_returns_graph(self):
        from dq.reports.date_checker.report import write_report
        with tempfile.TemporaryDirectory() as root, \
                patch('dq.stored.fields', return_value=[{'name': 'created_dt', 'type': 'pdate'}]), \
                patch('dq.stored.values', return_value=iter([('1', 'created_dt', '2024-01-01')])):
            paths = write_report('http://solr/c', os.path.join(root, 'date_checker.md'))
            with open(paths[0]) as stream:
                report = stream.read()
            self.assertIn('![Date distribution](created_dt_date_checker_dates.svg)', report)
            self.assertIn('[Open date graph](created_dt_date_checker_dates.svg)', report)
            self.assertIn('http://solr/c/select?', report)
            self.assertEqual(len(paths), 2)
            self.assertTrue(all(os.path.isfile(path) for path in paths))
