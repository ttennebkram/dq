"""Examples and boundaries for the bundled email and SSN processors."""
import unittest
from dq.processors.regex.definitions import definitions


class PresetTests(unittest.TestCase):
    def check_values(self, name, accepted, rejected):
        definition = definitions()[name]
        self.assertEqual(definition['results'], 'failed')
        _, kind, mode, patterns = definition['rules'][0]
        self.assertEqual((kind, mode), ('must_match', 'full'))
        for value in accepted:
            with self.subTest(value=value):
                self.assertTrue(any(pattern.fullmatch(value) for pattern in patterns))
        for value in rejected:
            with self.subTest(value=value):
                self.assertFalse(any(pattern.fullmatch(value) for pattern in patterns))

    def test_email(self):
        self.check_values('email',
            ['user@example.com', 'First.Last+tag@sub.example.org', "o'brien@example.com",
             'x#tag@example.com', 'a'*64+'@example.com'],
            ['', '@example.com', 'a..b@example.com', '.a@example.com',
             'a.@example.com', 'a@-example.com', 'a@example-.com', 'a@localhost',
             'a b@example.com', 'a@example.com\n', 'a'*65+'@example.com',
             'a@'+'b'*64+'.com', 'İ@example.com', 'a@examKple.com'])

    def test_ssn(self):
        # Synthetic structural examples, not assertions about issuance.
        self.check_values('ssn', ['123-45-6789', '123456789', '899-01-0001'],
            ['', '000-12-3456', '666-12-3456', '900-12-3456', '999123456',
             '123-00-4567', '123-45-0000', '123-456789', '12345-6789',
             '123 45 6789', '12345678', '1234567890', '１２３４５６７８９',
             ' 123-45-6789', '123-45-6789\n'])
