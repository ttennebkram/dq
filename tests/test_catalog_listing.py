"""Rule and report catalogs are target-free stdout commands."""
import io
import unittest
from unittest.mock import patch

from dq.main import main


class CatalogListingTests(unittest.TestCase):
    def run_catalog(self, option):
        with patch('dq.main.load_config') as load, patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(main([option]), 0)
        self.assertFalse(load.called)
        return out.getvalue()

    def test_list_reports_includes_status(self):
        output = self.run_catalog('--list_reports')
        self.assertIn('REPORT', output)
        self.assertIn('STATUS', output)
        self.assertRegex(output, r'(?m)^quick_checkup\s+Implemented\s+')
        self.assertNotIn('term_stats', output)
        self.assertNotIn('date_checker', output)

    def test_list_rules_includes_base_and_composite_types(self):
        output = self.run_catalog('--list_rules')
        self.assertIn('RULE', output)
        self.assertIn('TYPE', output)
        self.assertRegex(output, r'(?m)^email_base\s+Base\s+')
        self.assertRegex(output, r'(?m)^email_composite\s+Predefined Composite\s+')

    def test_hyphenated_aliases_remain_accepted(self):
        self.assertIn('Reports:', self.run_catalog('--list-reports'))
        self.assertIn('Rules:', self.run_catalog('--list-rules'))

    def test_catalog_is_exclusive_with_other_actions(self):
        for arguments in (['--list_rules', '--report', 'quick_checkup'],
                          ['--list_reports', '--list_fields'],
                          ['--list_rules', '--list_reports']):
            with self.subTest(arguments=arguments), patch('sys.stderr', io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                main(arguments)
            self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
