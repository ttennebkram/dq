"""Local login persistence without making changes to a Solr server."""
import os
import runpy
import stat
import tempfile
import unittest
from unittest.mock import patch

helper = runpy.run_path(os.path.join(os.path.dirname(__file__), '..', 'solr-auth'))
saved_credentials = helper['saved_credentials']


class SolrAuthHelperTests(unittest.TestCase):
    def test_first_prompt_then_reuse_and_explicit_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('builtins.input', return_value='solr'), \
                 patch('getpass.getpass', return_value='local%secret'), patch('builtins.print'):
                self.assertEqual(saved_credentials(directory), 'solr:local%secret')
            with patch('builtins.input', side_effect=AssertionError('must not prompt')), \
                 patch('getpass.getpass', side_effect=AssertionError('must not prompt')):
                self.assertEqual(saved_credentials(directory), 'solr:local%secret')
            path = os.path.join(directory, 'local-auth.ini')
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with patch('builtins.input', return_value='solr'), \
                 patch('getpass.getpass', return_value='replacement'), patch('builtins.print'):
                self.assertEqual(saved_credentials(directory, replace=True), 'solr:replacement')
            with open(path) as stream:
                text = stream.read()
                self.assertNotIn('local%secret', text)
                self.assertIn('replacement', text)

    def test_bad_username_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('builtins.input', return_value='bad:name'), \
                 patch('getpass.getpass', return_value='secret'):
                with self.assertRaises(ValueError):
                    saved_credentials(directory)
            self.assertFalse(os.path.exists(os.path.join(directory, 'local-auth.ini')))
