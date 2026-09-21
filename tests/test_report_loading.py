"""Report discovery, lazy imports, capabilities, and generic dispatch."""
import configparser
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import dq.rules
import dq.reports
from dq.arguments import build_parser, resolve_selection
from dq.main import main
from dq.findings import CsvExport
from dq.config import DqConfig
from dq.errors import ReportError
from dq.registry import load_handler


class LoadingTests(unittest.TestCase):
    def test_every_rule_ini_has_common_and_exactly_one_type_section(self):
        root = os.path.join(os.path.dirname(__file__), '..', 'src', 'dq', 'rules')
        names = [name for name in os.listdir(root)
                 if name.endswith(('_base', '_composite'))]
        self.assertEqual(len(names), 14)
        for name in names:
            parser = configparser.ConfigParser(interpolation=None)
            path = os.path.join(root, name, 'rule.ini')
            self.assertEqual(parser.read(path), [path], name)
            self.assertTrue(parser.has_section('rule'), name)
            self.assertTrue(parser.get('rule', 'description').strip(), name)
            expected = 'base_rule' if name.endswith('_base') else 'composite_rule'
            other = 'composite_rule' if expected == 'base_rule' else 'base_rule'
            self.assertTrue(parser.has_section(expected), name)
            self.assertFalse(parser.has_section(other), name)
            for shared in ('description', 'automatic_field_types',
                           'automatic_field_name_patterns'):
                for section in parser.sections():
                    if section != 'rule':
                        self.assertFalse(parser.has_option(section, shared),
                                         '{0}: {1} belongs under [rule]'.format(
                                             name, shared))

    def test_help_does_not_load_implementations(self):
        script = """
import sys
from dq.arguments import build_parser
build_parser().format_help()
assert 'dq.rules.missing_fields_base' not in sys.modules
assert 'dq.rules.missing_fields_base.processor' not in sys.modules
"""
        subprocess.check_call([sys.executable, '-c', script])

    def test_planned_or_unknown_names_do_not_load(self):
        for name, action in [('term_stats', 'report'), ('../../config', 'report'),
                             ('missing_fields_base', 'anything')]:
            with self.assertRaises(ReportError):
                load_handler(name, action)

    def test_planned_report_preflight_writes_nothing(self):
        with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.reports.quick_checkup.report.write_report') as report, \
                patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            main(['--report', 'quick_checkup', 'term_stats'])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse(report.called)

    def test_new_packages_use_their_directory_names(self):
        with tempfile.TemporaryDirectory() as directory:
            rule_root = os.path.join(directory, 'rules')
            report_root = os.path.join(directory, 'reports')
            os.mkdir(rule_root)
            os.mkdir(report_root)
            rule_package = os.path.join(rule_root, 'sample_base')
            report_package = os.path.join(report_root, 'sample_report')
            os.mkdir(rule_package)
            os.mkdir(report_package)
            with open(os.path.join(rule_package, '__init__.py'), 'w') as stream:
                stream.write('"""Sample base rule package."""\n')
            with open(os.path.join(rule_package, 'rule.ini'), 'w') as stream:
                stream.write('[rule]\ndescription = test rule\n[base_rule]\n')
            with open(os.path.join(report_package, '__init__.py'), 'w') as stream:
                stream.write("DESCRIPTION = 'test report'\n"
                             "REPORT = 'dq.reports.sample_report.impl:write_report'\n")
            with open(os.path.join(report_package, 'impl.py'), 'w') as stream:
                stream.write("def write_report(target, path, **kwargs):\n"
                             "    with open(path, 'w') as stream:\n"
                             "        stream.write('sample: ' + target)\n")
            try:
                with patch.object(dq.rules, '__path__', list(dq.rules.__path__) + [rule_root]), \
                        patch.object(dq.reports, '__path__', list(dq.reports.__path__) + [report_root]), \
                        patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                        patch('dq.actions.os.getcwd', return_value=directory), \
                        patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()) as err:
                    options = build_parser().parse_args(['--rule', 'sample_base'])
                    resolve_selection(options, build_parser())
                    self.assertEqual(options.rule, ['sample_base'])
                    self.assertEqual(options.action, 'csv')
                    self.assertIn('sample_base', build_parser().format_help())
                    self.assertEqual(main(['--report', 'sample_report']), 0)
                    with open(os.path.join(directory, 'reports', 'sample_report.md')) as stream:
                        self.assertEqual(stream.read(), 'sample: http://solr/c')
                    with patch('dq.reports.sample_report.REPORT', 'dq.config:load_config'):
                        with self.assertRaises(ReportError):
                            load_handler('sample_report', 'report')
            finally:
                for name in list(sys.modules):
                    if (name == 'dq.rules.sample_base' or name.startswith('dq.rules.sample_base.') or
                            name == 'dq.reports.sample_report' or name.startswith('dq.reports.sample_report.')):
                        del sys.modules[name]

    def test_id_failure_after_first_page_reports_partial_count(self):
        def pages(*args, **kwargs):
            yield [('one',)]
            raise ReportError('page unavailable')
        with tempfile.TemporaryDirectory() as directory:
            with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.actions.load_handler', return_value=lambda *a, **k: CsvExport([{'name': 'field_t'}], ['id'], pages())), \
                    patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()) as err, \
                    self.assertRaises(SystemExit) as error:
                main(['--rule', 'missing_fields_base', '--action', 'csv', '--reports_dir', directory])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(out.getvalue(), '')
            with open(os.path.join(directory, 'field_t_missing_fields_base.csv'), newline='') as stream:
                self.assertEqual(stream.read(), 'id\none\n')
            self.assertIn('export incomplete (1 CSV records written)', err.getvalue())
            self.assertNotIn('Wrote CSV:', err.getvalue())
