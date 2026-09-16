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
                 patch('dq.reports.checkup.collection_document_count', return_value=10), \
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
            self.assertIn('document counts for each selected field', text)
            self.assertNotIn('Stored values are not inspected', text)
            self.assertNotIn('None means', text)
            self.assertIn('For large collections, we suggest choosing specific fields', text)
            self.assertIn('`--rows` or its synonym `--size`', text)
            self.assertIn('perform these additional checks.\n\nFor large collections', text)
            self.assertIn('Additional checks in full report', text)
            self.assertIn('bin/dq --report full_checkup', text)
            self.assertIn('email', text)
            self.assertIn('Docs w/Value', text)
            self.assertLess(text.index('Docs w/Value'), text.index('Docs w/o Value'))
            self.assertRegex(text, r'`email_s`\s*\|\s*`unknown`\s*\|\s*7\s*\|\s*3\s*\|')
            self.assertLess(text.index('## Run Additional Checks'), text.index('## Full Report Workload Estimate'))

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
            self.assertRegex(report, r'`created_dt`[^\n]+Presence check only')
            self.assertNotIn('None means', report)
            self.assertNotIn('date_checker', report)
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
        self.assertIn('Documents to scan: 1,001', text)
        self.assertIn('Stored fields to fetch per document: 2', text)
        self.assertIn('approximately 2', text)
        self.assertIn('document/field pairs: 2,002', text)
        self.assertIn('Estimated stored-value scan time: 0.04-0.06 seconds', text)
        self.assertIn('Timing metric: 18,000-25,500 records/second on MacBook Pro M4', text)
        self.assertNotIn('Runtime: not estimated yet', text)

    def test_presence_only_has_no_scan(self):
        from dq.reports.checkup import _full_workload
        text = '\n'.join(_full_workload([{'name': 'vector'}],
                         {'vector': {'missing_fields_base': ''}}, 1001))
        self.assertIn('Collection documents: 1,001', text)
        self.assertIn('Fields with presence checks: 1', text)
        self.assertIn('Only field-presence checks are enabled', text)
        self.assertNotIn('Documents to scan: 0', text)
        self.assertNotIn('plus the unique key', text)

    def test_zero_rows_and_empty_collection_are_explained(self):
        from dq.reports.checkup import _full_workload
        fields = [{'name': 'notes_t'}]
        plans = {'notes_t': {'missing_fields_base': '', 'standard_text_composite': ''}}
        for total, limit, reason in [(10, 0, 'disabled by rows = 0'),
                                     (0, -1, 'collection is empty')]:
            text = '\n'.join(_full_workload(fields, plans, total, row_limit=limit))
            self.assertIn(reason, text)
            self.assertNotIn('Documents to scan: 0', text)
