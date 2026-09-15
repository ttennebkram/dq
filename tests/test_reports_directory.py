"""Report destination defaults, precedence and persistence."""
import os
import csv
import io
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from dq.main import main
from dq.findings import CsvExport
from dq.processors import ReportError
from dq.config import DqConfig, load_config, write_config
from dq.settings import reports_directory


class ReportDirectoryTests(unittest.TestCase):
    def test_default_is_reports_under_cwd(self):
        self.assertEqual(reports_directory(SimpleNamespace(reports_dir=None), DqConfig()),
                         os.path.join(os.getcwd(), 'reports'))

    def test_ini_relative_path_and_cli_override(self):
        with tempfile.TemporaryDirectory() as root:
            config = DqConfig(source=os.path.join(root, 'dq.ini'), reports_dir='results')
            self.assertEqual(reports_directory(SimpleNamespace(reports_dir=None), config),
                             os.path.join(root, 'results'))
            self.assertEqual(reports_directory(SimpleNamespace(reports_dir='chosen'), config),
                             os.path.join(os.getcwd(), 'chosen'))

    def test_config_round_trip_and_previous_value(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'dq.ini')
            write_config(path, 'http://localhost:8983/solr', 'demo', reports_dir='reports')
            self.assertEqual(load_config(path).reports_dir, 'reports')
            write_config(path, 'http://localhost:8983/solr', 'demo', reports_dir='results')
            self.assertEqual(load_config(path).reports_dir, 'results')
            with open(path) as stream:
                self.assertIn('# Previous reports_dir = reports', stream.read())


class OutputFileTests(unittest.TestCase):
    def csv_export(self, *args, **kwargs):
        return CsvExport([{'name': 'email_t'}], ['id', 'reason', 'value'], iter([[('001', 'email: bad, "format"', 'caf\u00e9\r\ntext')]]))

    def test_csv_default_creates_directory_and_preserves_utf8_csv(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'reports', 'email_t_email.csv')
            with patch('os.getcwd', return_value=root), \
                    patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.actions.load_handler', return_value=self.csv_export), \
                    patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()) as err:
                self.assertEqual(main(['--rule', 'email', '--action', 'csv']), 0)
                self.assertEqual(out.getvalue(), '\nFiles created:\n  reports/email_t_email.csv (1 data record; header not counted)\n')
                self.assertIn('Created reports directory: reports', err.getvalue())
                self.assertNotIn(root, out.getvalue())
                with open(path, encoding='utf-8', newline='') as stream:
                    self.assertEqual(list(csv.reader(stream)), [
                        ['id', 'reason', 'value'], ['001', 'email: bad, "format"', 'caf\u00e9\r\ntext']])
                with open(path, 'rb') as stream:
                    self.assertNotIn(b'\r\r\n', stream.read())
                # A rerun replaces the CSV, preserves the corresponding Markdown,
                # and does not announce creation of an existing directory.
                markdown = os.path.join(root, 'reports', 'email_t_email.md')
                with open(markdown, 'w') as stream:
                    stream.write('keep report')
                err.seek(0)
                err.truncate()
                with patch('dq.actions.load_handler', return_value=lambda *a, **k: CsvExport([{'name': 'email_t'}], ['id', 'reason', 'value'], iter([]))):
                    self.assertEqual(main(['--rule', 'email', '--action', 'csv']), 0)
                self.assertNotIn('Created reports directory:', err.getvalue())
                with open(path, newline='') as stream:
                    self.assertEqual(stream.read(), 'id,reason,value\r\n')
                with open(markdown) as stream:
                    self.assertEqual(stream.read(), 'keep report')

    def test_csv_honors_ini_relative_directory_and_cli_override(self):
        with tempfile.TemporaryDirectory() as root:
            config = DqConfig(main_url='http://solr/c', source=os.path.join(root, 'settings', 'dq.ini'),
                              reports_dir='results/nested')
            cases = [([], os.path.join(root, 'settings', 'results', 'nested')),
                     (['--reports_dir', 'chosen'], os.path.join(root, 'chosen'))]
            for arguments, expected in cases:
                with patch('os.getcwd', return_value=root), \
                        patch('dq.actions.load_config', return_value=config), \
                        patch('dq.actions.load_handler', return_value=self.csv_export), \
                        patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()) as err:
                    self.assertEqual(main(['--rule', 'email', '--action', 'csv'] + arguments), 0)
                self.assertTrue(os.path.isfile(os.path.join(expected, 'email_t_email.csv')))
                self.assertIn('Created reports directory: ' + os.path.relpath(expected, root), err.getvalue())

    def test_markdown_creates_directory_once_and_uses_report_name(self):
        def write_report(target, path, **kwargs):
            with open(path, 'w') as stream:
                stream.write('report')
        with tempfile.TemporaryDirectory() as root:
            directory = os.path.join(root, 'reports')
            with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.actions.load_handler', return_value=write_report), \
                    patch('sys.stdout', io.StringIO()) as out:
                for _ in range(2):
                    self.assertEqual(main(['--report', 'email', '--reports_dir', directory]), 0)
            self.assertTrue(os.path.isfile(os.path.join(directory, 'email.md')))
            self.assertEqual(out.getvalue().count('Created reports directory: '), 1)

    def test_csv_directory_error_fails_before_document_scan(self):
        scanned = []
        def pages():
            scanned.append(True)
            yield [('one',)]
        with tempfile.TemporaryDirectory() as root:
            blocked = os.path.join(root, 'blocked')
            with open(blocked, 'w') as stream:
                stream.write('keep')
            with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.actions.load_handler', return_value=lambda *a, **k: CsvExport([{'name': 'email_t'}], ['id'], pages())), \
                    patch('sys.stderr', io.StringIO()) as err, self.assertRaises(SystemExit) as error:
                main(['--rule', 'email', '--action', 'csv', '--reports_dir', os.path.join(blocked, 'reports')])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(scanned, [])
            self.assertIn('export incomplete (0 CSV records written)', err.getvalue())

    def test_invalid_selection_does_not_create_output_directory(self):
        with tempfile.TemporaryDirectory() as root:
            directory = os.path.join(root, 'reports')
            with patch('dq.actions.load_config', return_value=DqConfig(main_url='http://solr/c')), \
                    patch('dq.actions.load_handler', return_value=lambda *a, **k: (_ for _ in ()).throw(ReportError('invalid field'))), \
                    patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
                main(['--rule', 'email', '--action', 'csv', '--reports_dir', directory])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(os.path.exists(directory))
