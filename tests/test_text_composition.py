"""Shared text checks preserve ordering and do not duplicate fetching or findings."""
import unittest
from unittest.mock import patch
from dq.rules._text.processor import value_reasons
from dq.reports._checkup.processor import scan
from dq.rules.regex.engine import findings
from dq.rules.regex.definitions import definitions
from dq.registry import load_handler
from dq.rules.composites import COMPOSITES, expand
from dq.errors import ReportError


class CompositionTests(unittest.TestCase):
    def test_nested_composites_flatten_and_deduplicate_in_order(self):
        flattened = expand(['standard_text_composite', 'email_composite'],
                           ('missing_fields_base', 'empty_strings_base', 'whitespace_only_base',
                            'surrounding_whitespace_base', 'code_points_base', 'email_base'))
        self.assertEqual(flattened, ['missing_fields_base', 'empty_strings_base',
                         'whitespace_only_base', 'surrounding_whitespace_base',
                         'code_points_base', 'email_base'])

        part_number = expand(['part_number_example_composite'],
                             ('missing_fields_base', 'empty_strings_base', 'whitespace_only_base',
                              'surrounding_whitespace_base', 'code_points_base',
                              'part_number_example_base'))
        self.assertEqual(part_number, ['missing_fields_base', 'empty_strings_base',
                            'whitespace_only_base', 'surrounding_whitespace_base',
                            'code_points_base', 'part_number_example_base'])

    def test_composite_cycles_are_rejected(self):
        with patch.dict(COMPOSITES, {'cycle_a': {'rules': ('cycle_b',)},
                                    'cycle_b': {'rules': ('cycle_a',)}}):
            with self.assertRaises(ReportError) as error:
                expand(['cycle_a'], ())
        self.assertIn('cycle_a -> cycle_b -> cycle_a', str(error.exception))

    def test_base_and_composite_report_different_first_failures(self):
        source = [('1', 'email_t', 'person@example.com '),
                  ('2', 'email_t', None)]
        fields = [{'name': 'email_t', 'type': 'string', 'stored': True}]
        outputs = {}
        for rule in ('email_base', 'email_composite'):
            with patch('dq.stored.fields', return_value=fields), \
                    patch('dq.stored.values', return_value=iter(source)):
                _, pages = load_handler([rule], 'csv')('url')
                outputs[rule] = [row for page in pages for row in page]
        self.assertTrue(outputs['email_base'][0][1].startswith('email_base: no configured regex matched'))
        self.assertTrue(outputs['email_base'][1][1].startswith('email_base: no configured regex matched'))
        self.assertTrue(outputs['email_composite'][0][1].startswith('surrounding_whitespace_base:'))
        self.assertTrue(outputs['email_composite'][1][1].startswith('missing_fields_base:'))

    def test_order_and_empty_short_circuit(self):
        result = value_reasons(' \ufffd ')
        self.assertTrue(result[0].startswith('surrounding_whitespace_base:'))
        self.assertEqual(len(result), 1)
        self.assertTrue(value_reasons('\ufffd\u200b\ue000')[0].startswith('code_points_base:'))
        self.assertEqual(value_reasons('\ufffd\ue000'), [])
        with patch('dq.rules._text.processor.reasons') as unicode:
            expected = [(None, 'missing_fields_base: missing or null'),
                        ('', 'empty_strings_base: empty string'),
                        (' \t', 'whitespace_only_base: whitespace-only string')]
            for value, reason in expected:
                self.assertEqual(value_reasons(value), [reason])
            self.assertFalse(unicode.called)

    def test_checkup_shares_checks_across_specializations(self):
        source = [('1', 'contact_t', ''), ('2', 'contact_t', ' \ufffd ')]
        fields = [{'name':'contact_t','typeClass':'solr.TextField'}]
        plans = {'contact_t':dict((key,'explicit') for key in
                                  ('standard_text_composite','code_points_base','email_base','ssn_base'))}
        with patch('dq.stored.values', return_value=iter(source)) as fetch:
            result = scan('url',fields,plans)['contact_t']
        self.assertEqual(fetch.call_count,1)
        self.assertTrue(fetch.call_args[1]['include_null'])
        self.assertEqual(result['counts']['empty_strings_base'], 1)
        self.assertEqual(result['counts']['surrounding_whitespace_base'], 1)
        self.assertEqual(result['counts']['code_points_base'], 0)
        self.assertEqual(result['counts']['email_base'], 0)
        self.assertEqual(result['counts']['ssn_base'], 0)

    def test_regex_success_excludes_shared_failures(self):
        definition = dict(definitions()['email_base'], report='match')
        source = [('1','email_t',None),('2','email_t',''),('3','email_t','ok@example.com')]
        with patch('dq.stored.values', return_value=iter(source)) as fetch:
            rows = list(findings(definition,'url',[{'name':'email_t'}]))
        self.assertEqual(fetch.call_count,1)
        self.assertEqual([r[0] for r in rows],['3'])

    def test_code_points_base_standalone_is_unicode_only(self):
        with patch('dq.rules.code_points_base.processor.fields', return_value=[{'name':'id'}]), \
             patch('dq.stored.values',return_value=iter([
                 ('1','id',''),('2','id',' x '),('3','id','\ufffd\u200b\ue000')])) as fetch:
            _, pages = load_handler('code_points_base','csv')('url',include=['id'])
            rows = [row for page in pages for row in page]
        self.assertEqual(fetch.call_count,1)
        self.assertEqual([r[0] for r in rows],['3'])
        self.assertTrue(rows[0][1].startswith('code_points_base:'))


class DateMvpTests(unittest.TestCase):
    def test_native_dates_run_missing_fields_base_only(self):
        from dq.reports._checkup.processor import plan
        for name in ('event_date_dt', 'email_date', 'ssn_date'):
            field = {'name': name, 'type': 'pdate', 'typeClass': 'solr.DatePointField'}
            checks = plan(field)
            self.assertEqual(list(checks), ['missing_fields_base'])
            with patch('dq.stored.values', return_value=iter([
                    ('missing', name, None), ('present', name, '2024-01-01T00:00:00Z')])) as fetch:
                result = scan('url', [field], {name: checks})[name]
            self.assertTrue(fetch.called)
            self.assertEqual(result['counts']['missing_fields_base'], 1)

    def test_date_checker_is_deferred_for_both_actions(self):
        from dq.errors import ReportError
        from dq.registry import csv_names, report_help, rule_help
        self.assertNotIn('date_checker', csv_names())
        self.assertNotIn('date_checker', rule_help())
        self.assertNotIn('date_checker', report_help())
        for action in ('report', 'csv'):
            with self.assertRaises(ReportError) as error:
                load_handler('date_checker', action)
            self.assertIn('date_checker', str(error.exception))
