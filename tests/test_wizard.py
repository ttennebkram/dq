"""Interactive setup saves only after valid input and confirmation."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.main import main
from dq.config import load_config, write_config


class WizardTests(unittest.TestCase):
    def run_wizard(self, path, answers, extra=(), passwords=()):
        with patch('builtins.input', side_effect=list(answers)) as prompts, \
                patch('dq.wizard.getpass.getpass', side_effect=passwords) as password_prompt, \
                patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main(['--config_wizard', '--config', path] + list(extra)), 0)
            for call in prompts.call_args_list:
                self.assertFalse(any(word in call[0][0] for word in
                                     ('trust_certificate', 'include_fields', 'exclude_fields', 'pattern')))
            if not passwords:
                password_prompt.assert_not_called()
            return out.getvalue()

    def test_create_retry_target_and_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            output = self.run_wizard(path,
                ['ftp://localhost/solr', 'files', 'https://localhost:8984/solr', '', 'solr', ''],
                passwords=['private%secret'])
            config = load_config(path)
            self.assertEqual(config.collection, 'files')
            self.assertEqual(config.password, 'private%secret')
            self.assertIsNone(config.include_fields)
            self.assertIsNone(config.exclude_fields)
            self.assertNotIn('private%secret', output)
            self.assertIn('Invalid target', output)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_update_clear_auth_embedded_collection_preserves_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://localhost:8983/solr', 'old', username='solr',
                         password='oldsecret', include_fields=['old_*'])
            self.run_wizard(path, ['', '-', ''],
                            extra=['--main_url', 'http://localhost:8983/solr/new'])
            config = load_config(path)
            self.assertIsNone(config.collection)
            self.assertIsNone(config.username)
            self.assertIsNone(config.password)
            self.assertEqual(config.include_fields, ['old_*'])
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
            self.run_wizard(path, ['', '', '', 'n'])
            with patch('builtins.input', side_effect=EOFError), \
                    patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(['--config-wizard', '--config', path])
                self.assertEqual(error.exception.code, 130)
            with open(path, 'rb') as stream:
                self.assertEqual(before, stream.read())

    def test_new_setup_defaults_to_generated_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            self.run_wizard(path, [''] * 4)
            config = load_config(path)
            self.assertEqual(config.main_url, 'http://localhost:8983/solr')
            self.assertEqual(config.collection, 'dq-demo')

    def test_existing_and_cli_collection_override_demo_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://localhost:8983/solr', 'existing')
            self.run_wizard(path, [''] * 4)
            self.assertEqual(load_config(path).collection, 'existing')
            self.run_wizard(path, [''] * 4, extra=['--collection', 'chosen'])
            self.assertEqual(load_config(path).collection, 'chosen')

    def test_new_setup_with_embedded_collection_omits_demo_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            self.run_wizard(path, [''] * 3,
                            extra=['--main_url', 'http://localhost:8983/solr/embedded'])
            config = load_config(path)
            self.assertEqual(config.main_url, 'http://localhost:8983/solr/embedded')
            self.assertIsNone(config.collection)

    def test_blank_username_skips_password_and_clears_stale_credentials(self):
        for username in ('', '   '):
            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, 'dq.ini')
                write_config(path, 'http://localhost:8983/solr', 'dq-demo',
                             username=username, password='stale-password')
                self.run_wizard(path, [''] * 4)
                config = load_config(path)
                self.assertIsNone(config.username)
                self.assertIsNone(config.password)
                with open(path) as stream:
                    self.assertNotIn('stale-password', stream.read())

    def test_https_setup_needs_no_certificate_option(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            output = self.run_wizard(path, [''] * 4,
                                    extra=['--main_url', 'https://localhost:8984/solr'])
            config = load_config(path)
            self.assertEqual(config.main_url, 'https://localhost:8984/solr')
            self.assertIsNone(config.trust_certificate)
            self.assertNotIn('trust_certificate', output)

    def test_saved_certificate_preserved_without_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'https://localhost:8984/solr', 'dq-demo',
                         trust_certificate='certs/local.pem')
            with patch('dq.wizard.Connection'):
                self.run_wizard(path, [''] * 4)
            self.assertEqual(load_config(path).trust_certificate,
                             os.path.realpath(os.path.join(directory, 'certs/local.pem')))

    def test_setup_aliases_dispatch_to_the_same_wizard(self):
        for option in ('--config_wizard', '--config-wizard', '--setup_wizard', '--setup-wizard'):
            with patch('dq.wizard.run_wizard', return_value=0) as wizard:
                self.assertEqual(main([option, '--config', 'custom.ini']), 0)
                wizard.assert_called_once_with(wizard.call_args[0][0])
                options = wizard.call_args[0][0]
                self.assertTrue(options.config_wizard)
                self.assertEqual(options.config, 'custom.ini')

    def test_advanced_settings_preserved_without_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://localhost:8983/solr', 'dq-demo',
                         include_fields=['file_*'], exclude_fields=['*_vector'],
                         reports_dir='results')
            self.run_wizard(path, [''] * 4)
            config = load_config(path)
            self.assertEqual(config.include_fields, ['file_*'])
            self.assertEqual(config.exclude_fields, ['*_vector'])
            self.assertEqual(config.reports_dir, 'results')
            self.run_wizard(path, [''] * 4,
                            extra=['--include_fields', 'new_*', '--exclude_fields', ''])
            config = load_config(path)
            self.assertEqual(config.include_fields, ['new_*'])
            self.assertEqual(config.exclude_fields, [])

    def test_action_conflicts(self):
        for action in (['--write_config'], ['--list_fields'], ['--list_reports'],
                       ['--list_rules'], ['--report', 'quick_checkup'],
                       ['--rule', 'missing_fields_base', '--action', 'csv']):
            with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
                main(['--config_wizard'] + action)
            self.assertEqual(error.exception.code, 2)
