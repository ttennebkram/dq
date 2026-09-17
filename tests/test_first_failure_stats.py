"""First-failure CSV records and persisted completed-scan measurements."""
import csv
import io
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch
from dq.config import DqConfig
from dq.main import main
from dq.progress import ScanProgress
from dq.stats import FILENAME, save_scan_stats, note_rate
from dq.rules.regex.engine import findings
from dq.rules.code_points_base.processor import findings as unicode_findings
from dq.solr import SolrError


class FirstFailureTests(unittest.TestCase):
    def test_base_regex_stops_at_first_invalid_match(self):
        class NeverReached:
            def fullmatch(self, value):
                raise AssertionError('later regex must not run after failure')
        definition = {'name': 'test', 'report': 'match', 'rules': [
            ('regex01', 'partial', re.compile('.')),
            ('regex02', 'full', NeverReached())]}
        source = [('single', 'f', ' \ufffd '), ('multi', 'f', 'bad'), ('multi', 'f', 'also bad')]
        with patch('dq.stored.values', return_value=iter(source)) as fetch:
            rows = list(findings(definition, 'url', [{'name': 'f'}]))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual([row[0] for row in rows], ['single', 'multi', 'multi'])
        self.assertTrue(all('regex regex01 matched' in row[1] for row in rows))
        self.assertEqual([row[2] for row in rows], [row[2] for row in source])

    def test_code_points_base_reports_one_failure_per_value(self):
        value = '\ufffd\u200b\ue000'
        with patch('dq.stored.values', return_value=iter([('one', 'f', value)])):
            rows = list(unicode_findings('url', [{'name': 'f'}]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], value)


class StatsTests(unittest.TestCase):
    def test_measurements_append_preserve_units_and_omit_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = ScanProgress('missing_fields_base', 0, io.StringIO())
            with patch('dq.progress.time.monotonic', side_effect=[0, 2, 5, 5]):
                progress.start(['text_t'])
                progress.finish(1000)
                progress.start(['vector'], unit='missing documents')
                progress.finish(3)
            path = save_scan_stats(directory, 'https://user:password@solr/c?token=secret#fragment',
                                   'csv', 'missing_fields_base', progress, -1, False)
            note_rate(directory, 12586.5, 'Solr')
            with open(path) as stream:
                text = stream.read()
            records = [json.loads(line) for line in text.splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0]['target'], 'https://solr/c')
            self.assertEqual(records[0]['engine'], 'Solr')
            self.assertEqual(records[0]['records_checked'], 1000)
            self.assertEqual(records[0]['field_count'], 1)
            self.assertTrue(records[0]['machine'])
            self.assertEqual(records[0]['elapsed_seconds'], 2)
            self.assertEqual(records[0]['records_per_second'], 500)
            self.assertEqual(records[1]['count_unit'], 'missing documents')
            self.assertIsNone(records[1]['records_per_second'])
            self.assertEqual(records[2]['source'], 'user-reported')
            self.assertEqual(records[2]['engine'], 'Solr')
            self.assertTrue(records[2]['machine'])
            self.assertNotIn('fields', records[2])
            self.assertNotIn('password', text)
            self.assertNotIn('secret', text)

    def test_csv_success_records_document_count_and_failure_records_nothing(self):
        fields = [{'name': 'notes_t', 'type': 'string', 'stored': True}]
        page = {'response': {'docs': [{'dq_key': '001', 'dq_value0': ' bad '},
                                      {'dq_key': '002', 'dq_value0': 'good'}]}, 'nextCursorMark': 'one'}
        with tempfile.TemporaryDirectory() as directory, patch('os.getcwd', return_value=directory), \
                patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.stored.list_fields', return_value=fields), \
                patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()):
            with patch('dq.stored.get_json', side_effect=[{'uniqueKey': 'id'}, page]):
                self.assertEqual(main(['--rule', 'standard_text_composite', '--action', 'csv', '--rows', '2']), 0)
            path = os.path.join(directory, 'reports', FILENAME)
            with open(path) as stream:
                original = stream.read()
            record = json.loads(original)
            self.assertEqual(record['records_checked'], 2)
            self.assertEqual(record['fields'], ['notes_t'])
            self.assertEqual(record['field_count'], 1)
            self.assertEqual(record['name'], 'standard_text_composite')
            self.assertIn('reports/' + FILENAME, out.getvalue())
            self.assertNotIn(' bad ', original)
            with open(os.path.join(directory, 'reports', 'notes_t_standard_text_composite.csv')) as stream:
                self.assertEqual(len(list(csv.reader(stream))), 2)
            with patch('dq.stored.get_json', side_effect=[{'uniqueKey': 'id'}, page]), \
                    patch('sys.stdout', io.StringIO()) as second_out:
                self.assertEqual(main(['--rule', 'standard_text_composite', '--action', 'csv', '--rows', '2']), 0)
            self.assertIn('Files updated:\n  reports/' + FILENAME, second_out.getvalue())
            with open(path) as stream:
                original = stream.read()
            with patch('dq.stored.get_json', side_effect=SolrError('failure')), self.assertRaises(SystemExit):
                main(['--rule', 'standard_text_composite', '--action', 'csv', '--rows', '2'])
            with open(path) as stream:
                self.assertEqual(stream.read(), original)

    def test_no_scan_does_not_write_stats_and_save_errors_are_nonfatal(self):
        progress = ScanProgress('full_checkup', stream=io.StringIO())
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(save_scan_stats(directory, 'url', 'report', 'full_checkup', progress, 0, False))
            self.assertEqual(os.listdir(directory), [])
            progress.measurements = [{'records_checked': 1}]
            with patch('dq.stats.append_records', side_effect=OSError('read only')), patch('sys.stderr', io.StringIO()) as err:
                self.assertIsNone(save_scan_stats(directory, 'url', 'report', 'full_checkup', progress, -1, False))
            self.assertIn('could not save processing stats', err.getvalue())
