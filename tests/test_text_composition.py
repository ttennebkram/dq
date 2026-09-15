"""Shared text checks preserve ordering and do not duplicate fetching or findings."""
import unittest
from unittest.mock import patch
from dq.processors.standard_text.processor import value_reasons
from dq.processors._checkup.processor import scan
from dq.processors.regex.engine import findings
from dq.processors.regex.definitions import definitions
from dq.processors.registry import load_handler


class CompositionTests(unittest.TestCase):
    def test_order_and_empty_short_circuit(self):
        result = value_reasons(' \ufffd ')
        self.assertTrue(result[0].startswith('surrounding_whitespace:'))
        self.assertEqual(len(result), 1)
        self.assertTrue(value_reasons('\ufffd')[0].startswith('code_points:'))
        with patch('dq.processors.standard_text.processor.reasons') as unicode:
            for value, reason in [(None, 'null'), ('', 'empty string'), (' \t', 'whitespace only')]:
                self.assertEqual(value_reasons(value), ['empty_values: ' + reason])
            self.assertFalse(unicode.called)

    def test_checkup_shares_checks_across_specializations(self):
        source = [('1', 'contact_t', ''), ('2', 'contact_t', ' \ufffd ')]
        fields = [{'name':'contact_t','typeClass':'solr.TextField'}]
        plans = {'contact_t':dict((key,'explicit') for key in ('standard_text','code_points','email','ssn'))}
        with patch('dq.stored.values', return_value=iter(source)) as fetch:
            result = scan('url',fields,plans)['contact_t']
        self.assertEqual(fetch.call_count,1)
        self.assertTrue(fetch.call_args[1]['include_null'])
        self.assertEqual(result['counts']['standard_text'],2)
        self.assertEqual(result['counts']['code_points'],0)
        self.assertEqual(result['counts']['email'],0)
        self.assertEqual(result['counts']['ssn'],0)
        self.assertEqual(sum('empty_values' in r[1] for r in result['examples']),1)

    def test_regex_success_excludes_shared_failures(self):
        definition = dict(definitions()['email'], results='succeeded')
        source = [('1','email_t',None),('2','email_t',''),('3','email_t','ok@example.com')]
        with patch('dq.stored.values', return_value=iter(source)) as fetch:
            rows = list(findings(definition,'url',[{'name':'email_t'}]))
        self.assertEqual(fetch.call_count,1)
        self.assertEqual([r[0] for r in rows],['3'])

    def test_code_points_standalone_is_unicode_only(self):
        with patch('dq.processors.code_points.processor.fields', return_value=[{'name':'id'}]), \
             patch('dq.stored.values',return_value=iter([('1','id',''),('2','id',' x '),('3','id','\ufffd')])) as fetch:
            _, pages = load_handler('code_points','csv')('url',include=['id'])
            rows = [row for page in pages for row in page]
        self.assertEqual(fetch.call_count,1)
        self.assertEqual([r[0] for r in rows],['3'])
        self.assertTrue(rows[0][1].startswith('code_points:'))


class DateMvpTests(unittest.TestCase):
    def test_native_dates_are_presence_only_even_with_value_overrides(self):
        from dq.processors._checkup.processor import plan
        for name in ('event_date_dt', 'email_date', 'ssn_date'):
            field = {'name': name, 'type': 'pdate', 'typeClass': 'solr.DatePointField'}
            for rules in ([], [('*', ['missing_fields', 'empty_values', 'standard_text', 'email'])]):
                checks = plan(field, rules)
                self.assertEqual(list(checks), ['missing_fields'])
                with patch('dq.stored.values') as fetch:
                    result = scan('url', [field], {name: checks})[name]
                self.assertFalse(fetch.called)
                self.assertEqual(sum(result['counts'].values()), 0)

    def test_date_checker_is_deferred_for_both_actions_and_overrides(self):
        import os
        import tempfile
        from dq.processors import ReportError
        from dq.processors._checkup.processor import overrides
        from dq.processors.registry import csv_names, report_help, rule_help
        self.assertNotIn('date_checker', csv_names())
        self.assertNotIn('date_checker', rule_help())
        date_line = next(line for line in report_help().splitlines() if 'date_checker' in line)
        self.assertIn('PLANNED', date_line)
        for action in ('report', 'csv'):
            with self.assertRaises(ReportError) as error:
                load_handler('date_checker', action)
            self.assertIn('deferred beyond the MVP', str(error.exception))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            with open(path, 'w') as stream:
                stream.write('[checkup]\n* = missing_fields, date_checker\n')
            with self.assertRaises(ReportError):
                overrides(path)
