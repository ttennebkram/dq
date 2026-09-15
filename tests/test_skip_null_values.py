"""Null-only filtering retains other text findings across CLI, CSV, and reports."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.arguments import build_parser
from dq.config import DqConfig, ConfigError, load_config, write_config
from dq.main import main
from dq.settings import resolve_skip_null_values
from dq.processors.registry import load_handler
from dq.processors.regex.definitions import definitions
from dq.processors.regex.engine import findings
from dq.processors._checkup.processor import scan
from dq.processors.standard_text.processor import value_reasons


FIELDS = [{'name': 'email_t', 'type': 'string', 'stored': True}]
VALUES = [None, '', ' \t', ' x ', '\ufffd', 'bad', 'ok@example.com']
SOURCE = [(str(i), 'email_t', value) for i, value in enumerate(VALUES)]


class NullFilterTests(unittest.TestCase):
    def test_only_none_is_suppressed(self):
        self.assertEqual(value_reasons(None), ['empty_values: null'])
        self.assertEqual(value_reasons(None, True), [])
        for value in VALUES[1:] + [0, False]:
            self.assertEqual(value_reasons(value, True), value_reasons(value))

    def test_standard_and_regex_csv_retain_whitespace_and_other_findings(self):
        for name in ('standard_text', 'email'):
            outputs = []
            for skip in (False, True):
                with patch('dq.stored.fields', return_value=FIELDS), patch('dq.stored.values', return_value=iter(SOURCE)) as fetch:
                    _, pages = load_handler(name, 'csv')('url', skip_null_values=skip)
                    outputs.append([row for page in pages for row in page])
                self.assertEqual(fetch.call_count, 1)
            self.assertEqual(outputs[1], [row for row in outputs[0] if row[0] != '0'])
            self.assertTrue(set(('1', '2', '3', '4')).issubset(row[0] for row in outputs[1]))

    def test_regex_success_never_includes_null_or_blank(self):
        definition = dict(definitions()['email'], results='succeeded')
        with patch('dq.stored.values', return_value=iter(SOURCE)):
            rows = list(findings(definition, 'url', FIELDS, skip_null_values=True))
        self.assertEqual([row[0] for row in rows], ['6'])

    def test_checkup_counts_drop_only_null_finding(self):
        plans = {'email_t': dict((name, 'test') for name in ('missing_fields', 'standard_text', 'email'))}
        outputs = []
        for skip in (False, True):
            with patch('dq.stored.values', return_value=iter(SOURCE)):
                outputs.append(scan('url', FIELDS, plans, skip_null_values=skip)['email_t'])
        self.assertEqual(outputs[1]['counts']['standard_text'], outputs[0]['counts']['standard_text'] - 1)
        self.assertEqual(outputs[1]['counts']['email'], outputs[0]['counts']['email'])
        self.assertEqual(outputs[1]['examples'], [row for row in outputs[0]['examples'] if row[0] != '0'])

    def test_cli_bool_override_and_invalid_value(self):
        parser = build_parser()
        for args, expected in [([], False), (['--skip_null_values'], True), (['--skip-null-values'], True),
                               (['--skip_null_values', 'false'], False)]:
            self.assertEqual(resolve_skip_null_values(parser.parse_args(args), DqConfig()), expected)
        self.assertFalse(resolve_skip_null_values(parser.parse_args(['--skip_null_values=false']), DqConfig(skip_null_values=True)))
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(['--skip_null_values', 'sometimes'])

    def test_config_roundtrip_precedence_preservation_and_wizard(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'dq.ini')
            with open(path, 'w') as stream:
                stream.write('[DEFAULT]\nmain_url=http://solr/c\nskip_null_values=false\n[dq]\nskip_null_values=true\n')
            self.assertTrue(load_config(path).skip_null_values)
            with patch('os.getcwd', return_value=root):
                self.assertTrue(load_config().skip_null_values)
            with patch('sys.stdout', io.StringIO()):
                main(['--write_config', '--config', path])
            self.assertTrue(load_config(path).skip_null_values)
            with patch('sys.stdout', io.StringIO()), patch('builtins.input', side_effect=[''] * 3) as prompts:
                main(['--config_wizard', '--config', path])
            self.assertEqual(prompts.call_count, 3)
            self.assertTrue(load_config(path).skip_null_values)
            with patch('sys.stdout', io.StringIO()):
                main(['--write_config', '--config', path, '--skip_null_values', 'false'])
            self.assertFalse(load_config(path).skip_null_values)
            with open(path) as stream:
                self.assertIn('# Previous skip_null_values = true', stream.read())
            with open(path, 'w') as stream:
                stream.write('[DEFAULT]\nskip_null_values=typo\n')
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_report_effective_value_provenance_and_null_suppression(self):
        for action in ('full_checkup',):
            with tempfile.TemporaryDirectory() as root, patch('os.getcwd', return_value=root), \
                    patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.reports.checkup.list_fields', return_value=FIELDS), \
                    patch('dq.reports.checkup.collection_document_count', return_value=7), \
                    patch('dq.reports.checkup.field_document_count', return_value=6), \
                    patch('dq.stored.values', return_value=iter(SOURCE)), patch('sys.stdout', io.StringIO()):
                self.assertEqual(main(['--report', action, '--skip_null_values']), 0)
                with open(os.path.join(root, 'reports', 'email_t_' + action + '.md')) as stream:
                    report = stream.read()
                self.assertNotIn('empty_values: null', report)
                self.assertIn('empty_values: empty string', report)
                self.assertIn('empty_values: whitespace only', report)
                self.assertTrue(any('skip_null_values' in line and 'true' in line and 'command line' in line for line in report.splitlines()))
