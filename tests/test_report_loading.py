"""Report discovery, lazy imports, capabilities, and generic dispatch."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import dq.processors
from dq.arguments import build_parser, resolve_selection
from dq.main import main
from dq.findings import CsvExport
from dq.config import DqConfig
from dq.processors import ReportError
from dq.processors.registry import load_handler


class LoadingTests(unittest.TestCase):
    def test_help_does_not_load_implementations(self):
        script = """
import sys
from dq.arguments import build_parser
build_parser().format_help()
assert 'dq.processors.missing_fields' in sys.modules
assert 'dq.processors.missing_fields.processor' not in sys.modules
"""
        subprocess.check_call([sys.executable, '-c', script])

    def test_planned_or_unknown_names_do_not_load(self):
        for name, action in [('term_stats', 'report'), ('../../config', 'report'),
                             ('missing_fields', 'anything')]:
            with self.assertRaises(ReportError):
                load_handler(name, action)

    def test_planned_report_preflight_writes_nothing(self):
        with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                patch('dq.reports.quick_checkup.write_report') as report, \
                patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            main(['--report', 'quick_checkup', 'term_stats'])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse(report.called)

    def test_new_package_discovered_and_dispatched_without_cli_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            package = os.path.join(directory, 'sample')
            os.mkdir(package)
            with open(os.path.join(package, '__init__.py'), 'w') as stream:
                stream.write("NAME = 'sample'\nDESCRIPTION = 'test report'\n"
                             "REPORT = 'dq.processors.sample.impl:write_report'\n"
                             "RULE_TYPE = 'base'\n"
                             "CSV = 'dq.processors.sample.impl:prepare_csv'\n")
            with open(os.path.join(package, 'impl.py'), 'w') as stream:
                stream.write("from dq.findings import CsvExport\n"
                             "def write_report(target, path, **kwargs):\n"
                             "    with open(path, 'w') as stream:\n"
                             "        stream.write('sample: ' + target)\n"
                             "def prepare_csv(target, **kwargs):\n"
                             "    return CsvExport([{'name': 'field_t'}], ['id'], iter([[('one',), ('two',)]]))\n")
            try:
                with patch.object(dq.processors, '__path__', list(dq.processors.__path__) + [directory]), \
                        patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                        patch('dq.actions.os.getcwd', return_value=directory), \
                        patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()) as err:
                    options = build_parser().parse_args(['--rule', 'sample', '--action', 'csv'])
                    resolve_selection(options, build_parser())
                    self.assertEqual(options.rule, ['sample'])
                    self.assertEqual(options.action, 'csv')
                    self.assertIn('sample', build_parser().format_help())
                    self.assertEqual(main(['--report', 'sample']), 0)
                    with open(os.path.join(directory, 'reports', 'sample.md')) as stream:
                        self.assertEqual(stream.read(), 'sample: http://solr/c')
                    out.seek(0)
                    out.truncate()
                    self.assertEqual(main(['--rule', 'sample', '--action', 'csv']), 0)
                    self.assertEqual(out.getvalue(), '\nFiles created:\n  reports/field_t_sample.csv (2 data records; header not counted)\n')
                    with open(os.path.join(directory, 'reports', 'field_t_sample.csv'), newline='') as stream:
                        self.assertEqual(stream.read(), 'id\r\none\r\ntwo\r\n')
                    self.assertIn('Offending records exported: 2', err.getvalue())
                    with patch('dq.processors.sample.CSV', None):
                        with self.assertRaises(ReportError):
                            load_handler('sample', 'csv')
                    with patch('dq.processors.sample.REPORT', 'dq.config:load_config'):
                        with self.assertRaises(ReportError):
                            load_handler('sample', 'report')
            finally:
                for name in list(sys.modules):
                    if name == 'dq.processors.sample' or name.startswith('dq.processors.sample.'):
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
                main(['--rule', 'missing_fields', '--action', 'csv', '--reports_dir', directory])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(out.getvalue(), '')
            with open(os.path.join(directory, 'field_t_missing_fields.csv'), newline='') as stream:
                self.assertEqual(stream.read(), 'id\r\none\r\n')
            self.assertIn('export incomplete (1 CSV records written)', err.getvalue())
            self.assertNotIn('Wrote CSV:', err.getvalue())
