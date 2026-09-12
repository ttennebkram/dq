"""Interactive setup saves only after valid input and confirmation."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.cli import main
from dq.config import load_config, write_config


class WizardTests(unittest.TestCase):
    def run_wizard(self, path, answers, extra=(), passwords=()):
        with patch('builtins.input', side_effect=answers), \
                patch('dq.wizard.getpass.getpass', side_effect=passwords), \
                patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main(['--config_wizard', '--config', path] + list(extra)), 0)
            return out.getvalue()

    def test_create_retry_target_filters_and_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            output = self.run_wizard(path,
                ['ftp://localhost/solr', 'files', 'https://localhost:8984/solr', '', 'solr', '',
                 'file_*', 'title[ab,]_s', '', '*_vector', '', ''],
                passwords=['private%secret'])
            config = load_config(path)
            self.assertEqual(config.collection, 'files')
            self.assertEqual(config.password, 'private%secret')
            self.assertEqual(config.include_fields, ['file_*', 'title[ab,]_s'])
            self.assertEqual(config.exclude_fields, ['*_vector'])
            self.assertNotIn('private%secret', output)
            self.assertIn('Invalid target', output)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_update_clear_auth_embedded_collection_and_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://localhost:8983/solr', 'old', username='solr',
                         password='oldsecret', include_fields=['old_*'])
            self.run_wizard(path, ['', '-', '', '-', '', ''],
                            extra=['--main_url', 'http://localhost:8983/solr/new'])
            config = load_config(path)
            self.assertIsNone(config.collection)
            self.assertIsNone(config.username)
            self.assertIsNone(config.password)
            self.assertEqual(config.include_fields, [])
            with open(path) as stream:
                text = stream.read()
            self.assertIn('# Previous collection = old', text)
            self.assertNotIn('oldsecret', text)

    def test_decline_and_eof_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://localhost:8983/solr', 'files')
            with open(path, 'rb') as stream:
                before = stream.read()
            self.run_wizard(path, ['', '', '', '', '', '', 'n'])
            with patch('builtins.input', side_effect=EOFError), \
                    patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(['--config-wizard', '--config', path])
                self.assertEqual(error.exception.code, 130)
            with open(path, 'rb') as stream:
                self.assertEqual(before, stream.read())

    def test_action_conflicts(self):
        for action in (['--write_config'], ['--list_fields'], ['--report', 'empty_fields'], ['--ids', 'empty_fields']):
            with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
                main(['--config_wizard'] + action)
            self.assertEqual(error.exception.code, 2)
