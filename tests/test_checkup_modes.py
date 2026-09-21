"""Lite must never scan stored values or present suggestions as completed tests."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.registry import load_handler, report_help
from dq.errors import ReportError
from dq.config import DqConfig
from dq.main import main


class CheckupModeTests(unittest.TestCase):
    def test_quick_skips_scan_and_uses_matching_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, 'quick_checkup.md')
            with patch('sys.stdout', io.StringIO()) as stdout, \
                 patch('dq.reports.checkup.list_fields', return_value=[{'name':'email_s', 'stored':True}]), \
                 patch('dq.reports.checkup.collection_document_count', side_effect=[10, 11]), \
                 patch('dq.reports.checkup.field_document_count', return_value=7), \
                 patch('dq.reports.checkup.scan') as scan, \
                 patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')):
                self.assertEqual(main(['--report', 'quick_checkup', '--reports_dir', directory]), 0)
            self.assertFalse(scan.called)
            self.assertEqual(stdout.getvalue(), '\nMain Report File:\n  ' + os.path.relpath(os.path.realpath(output), os.path.realpath(os.getcwd())) + '\n')
            self.assertEqual(os.listdir(directory), ['quick_checkup.md'])
            with open(output) as stream:
                text = stream.read()
            self.assertIn('Report: `quick_checkup`', text)
            self.assertIn('count documents with and without a value for each selected field', text)
            self.assertNotIn('Stored values are not inspected', text)
            self.assertNotIn('None means', text)
            self.assertIn('Run a detailed report with:', text)
            self.assertIn('bin/dq --report full_checkup', text)
            self.assertIn('For large collections, during testing, consider limiting records with `--rows` or `--size`', text)
            self.assertIn('Matching Rule', text)
            self.assertIn('bin/dq --report full_checkup', text)
            self.assertIn('email', text)
            self.assertIn('Docs w/Value', text)
            self.assertIn('Fields in collection/index `c`, which contains 11 documents:', text)
            self.assertIn('- Collection: `c`', text)
            self.assertNotIn('- Collection: `http://solr/c`', text)
            self.assertIn('Browse documents in Solr: <http://solr/c/select?q=*:*>', text)
            self.assertNotIn('Document counts come from Solr', text)
            self.assertLess(text.index('Docs w/Value'), text.index('Docs w/o Value'))
            self.assertRegex(text, r'`email_s`\s*\|\s*`unknown`\s*\|\s*7\s*\|\s*3\s*\|')
            self.assertNotIn('## Full Report Workload Estimate', text)
            self.assertLess(text.index('## Results'), text.index('## Run Additional Checks'))
            self.assertLess(text.index('## Run Additional Checks'), text.index('## Summary'))
            self.assertLess(text.index('## Summary'), text.index('## Options Used'))

    def test_presence_only_label(self):
        from dq.reports.checkup import write_report
        with tempfile.TemporaryDirectory() as directory:
            fields = [{'name': 'created_dt', 'type': 'pdate', 'stored': True}]
            path = os.path.join(directory, 'quick_checkup.md')
            with patch('dq.reports.checkup.list_fields', return_value=fields), \
                    patch('dq.reports.checkup.collection_document_count', return_value=1000), \
                    patch('dq.reports.checkup.field_document_count', return_value=990), \
                    patch('dq.reports.checkup.scan') as scan:
                write_report('http://solr/c', path, mode='lite')
            self.assertFalse(scan.called)
            with open(path) as stream:
                report = stream.read()
            self.assertRegex(report, r'`created_dt`[^\n]+missing_fields_base')
            self.assertNotIn('None means', report)
            self.assertNotIn('date_checker', report)
            self.assertNotIn('### `created_dt`', report)
            self.assertIn('bin/dq --include_field created_dt --rule missing_fields_base', report)
            self.assertNotIn('--config dq.ini', report)

    def test_full_dispatch_and_help(self):
        with patch('dq.reports.full_checkup.report._write_report') as write:
            load_handler('full_checkup', 'report')('url', 'report.md')
        self.assertEqual(write.call_args[1]['mode'], 'full')
        self.assertEqual(write.call_args[1]['report_name'], 'full_checkup')
        for name in ('quick_checkup', 'full_checkup'):
            self.assertIn(name, report_help())
            with self.assertRaises(ReportError):
                load_handler(name, 'csv')

    def test_retired_names_are_not_report_aliases(self):
        from dq.registry import report_names
        for name in ('checkup_lite', 'checkup_quick', 'checkup_full', 'checkup'):
            self.assertNotIn(name, report_names())
            with self.assertRaises(ReportError):
                load_handler(name, 'report')


class WorkloadTests(unittest.TestCase):
    def test_shared_scan_pages_and_vector_exclusion(self):
        from dq.reports.checkup import _full_workload
        fields = [{'name': 'email'}, {'name': 'text'}, {'name': 'vector'}]
        plans = {'email': {'missing_fields_base': '', 'email_composite': ''},
                 'text': {'standard_text_composite': ''}, 'vector': {'missing_fields_base': ''}}
        text = '\n'.join(_full_workload(fields, plans, 1001))
        self.assertIn('Estimated time:', text)
        self.assertIn('to scan all records and all fields', text)
        self.assertIn('reference Solr timing on MacBook Pro M4', text)
        self.assertIn('0.063-0.065 seconds', text)
        self.assertNotIn('| Planned value check', text)

    def test_elasticsearch_opensearch_estimate_uses_its_own_timing(self):
        from dq.reports.checkup import _full_workload
        fields = [{'name': 'email'}]
        plans = {'email': {'email_composite': ''}}
        text = '\n'.join(_full_workload(
            fields, plans, 1000, engine='Elasticsearch/OpenSearch'))
        self.assertIn('reference Elasticsearch/OpenSearch timing on MacBook Pro M4', text)
        self.assertIn('0.060-0.060 seconds', text)
        self.assertNotIn('Solr 9.10.1', text)

    def test_missing_only_rule_is_included_in_scan_estimate(self):
        from dq.reports.checkup import _full_workload
        text = '\n'.join(_full_workload([{'name': 'vector'}],
                         {'vector': {'missing_fields_base': ''}}, 1001))
        self.assertIn('to scan all records and all fields', text)

    def test_zero_rows_and_empty_collection_are_explained(self):
        from dq.reports.checkup import _full_workload
        fields = [{'name': 'notes_t'}]
        plans = {'notes_t': {'missing_fields_base': '', 'standard_text_composite': ''}}
        for total, limit, reason in [(10, 0, 'disabled by `--rows 0`'),
                                     (0, -1, 'collection is empty')]:
            text = '\n'.join(_full_workload(fields, plans, total, row_limit=limit))
            self.assertIn(reason, text)
            self.assertNotIn('scan up to 0', text)
