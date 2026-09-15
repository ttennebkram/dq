"""Precise CSV rules for missing, empty, and whitespace-only values."""
import unittest
from unittest.mock import patch
from dq.processors import ReportError
from dq.processors.registry import csv_names, discover, load_handler, report_names, rule_help


def records(export):
    return [tuple(row) for page in export.pages for row in page]


class ValueStateRuleTests(unittest.TestCase):
    def test_registry_exposes_precise_csv_rules_only(self):
        self.assertIn('missing_fields', csv_names())
        self.assertIn('empty_strings', csv_names())
        self.assertIn('whitespace_only', csv_names())
        self.assertNotIn('empty_fields', csv_names())
        self.assertNotIn('empty_fields', report_names())
        self.assertNotIn('null_fields', csv_names())
        with self.assertRaises(ReportError):
            load_handler('null_fields', 'csv')

    def test_registry_classifies_base_and_predefined_composite_rules(self):
        entries = discover()
        self.assertEqual(entries['missing_fields']['rule_type'], 'base')
        self.assertEqual(entries['standard_text']['rule_type'], 'composite')
        help_text = rule_help()
        self.assertRegex(help_text, r'(?m)^  standard_text\s+composite\s+')
        self.assertRegex(help_text, r'(?m)^  email\s+base\s+')

    def test_missing_fields_selects_only_absent_or_null_values(self):
        field = {'name': 'email_t', 'stored': True, 'type': 'text_general'}
        values = iter([('a', 'email_t', False), ('b', 'email_t', True),
                       ('c', 'email_t', True)])
        with patch('dq.processors.missing_fields.processor.list_fields', return_value=[field]), \
                patch('dq.stored.values', return_value=values):
            export = load_handler('missing_fields', 'csv')('url', row_limit=3)
            self.assertEqual(export.header, ['id', 'reason', 'value'])
            self.assertEqual(records(export),
                             [('a', 'missing_fields: missing or null', '')])

    def test_empty_and_whitespace_rules_do_not_overlap(self):
        field = {'name': 'email_t', 'stored': True, 'type': 'text_general'}
        source = [('a', 'email_t', ''), ('b', 'email_t', ' '),
                  ('c', 'email_t', '\t\n'), ('d', 'email_t', 'value')]
        for name, expected in [
                ('empty_strings', [('a', 'empty_strings: empty string', '')]),
                ('whitespace_only', [
                    ('b', 'whitespace_only: whitespace-only string', ' '),
                    ('c', 'whitespace_only: whitespace-only string', '\t\n')])]:
            module = 'dq.processors.' + name + '.processor'
            with patch(module + '.stored.fields', return_value=[field]), \
                    patch(module + '.stored.values', return_value=iter(source)):
                self.assertEqual(records(load_handler(name, 'csv')('url')), expected)

    def test_missing_fields_combines_with_other_rules_in_one_record_scan(self):
        field = {'name': 'notes_t', 'stored': True, 'type': 'text_general'}
        source = [('a', 'notes_t', None), ('b', 'notes_t', '  '),
                  ('c', 'notes_t', 'value')]
        with patch('dq.processors.chain.stored.fields', return_value=[field]), \
                patch('dq.processors.chain.stored.values', return_value=iter(source)) as scan:
            export = load_handler(['missing_fields', 'whitespace_only'], 'csv')('url')
            self.assertEqual(records(export), [
                ('a', 'missing_fields: missing or null', ''),
                ('b', 'whitespace_only: whitespace-only string', '  '),
            ])
        self.assertEqual(scan.call_count, 1)
        self.assertTrue(scan.call_args[1]['include_null'])


if __name__ == '__main__':
    unittest.main()
