"""Reproducible per-field defect rates and boundary validation."""
import runpy
from types import SimpleNamespace
import json
import os
import io
import re
import random
import tempfile
from unittest.mock import Mock, patch
import unittest
from dq.rules.regex.definitions import definitions
from dq.rules.code_points_base.processor import failure_reason as code_point_failure_reason

path = os.path.join(os.path.dirname(__file__), '..', 'generate_test_collection', 'data_generator_common.py')
demo = SimpleNamespace(**runpy.run_path(path))


def valid_values(index):
    """Read deterministic valid values through the shared seeded API."""
    return demo.valid_values(index, random.Random(0))


class DemoGeneratorTests(unittest.TestCase):
    def test_exact_percent_per_field_and_reproducibility(self):
        docs, seed = demo.generate(100, seed=42)
        self.assertEqual((docs, seed), demo.generate(100, seed=42))
        for field in demo.FIELDS:
            errors = [doc for index, doc in enumerate(docs, 1)
                      if doc.get(field) != valid_values(index)[field]]
            self.assertEqual(len(errors), 20)

    def test_global_percentage_rounding_and_limits(self):
        docs, _ = demo.generate(10, 25, seed=42)
        for field in demo.FIELDS:
            errors = [doc for index, doc in enumerate(docs, 1)
                      if doc.get(field) != valid_values(index)[field]]
            self.assertEqual(len(errors), 3)
        for kwargs in ({'count':0}, {'incorrect_percent':101}, {'incorrect_percent':float('nan')}):
            with self.assertRaises(ValueError):
                demo.generate(**dict({'count':100}, **kwargs))

    def test_part_numbers_include_valid_and_varied_invalid_values(self):
        pattern = re.compile(r'^[A-Za-z]{3}-[0-9]{6}$')
        self.assertTrue(pattern.match(valid_values(7)['part_number_s']))
        docs, _ = demo.generate(100, incorrect_percent=20, seed=42)
        values = [doc['part_number_s'] for index, doc in enumerate(docs, 1)
                  if isinstance(doc.get('part_number_s'), str)
                  and doc['part_number_s']
                  and doc['part_number_s'].strip()
                  and doc['part_number_s'] != valid_values(index)['part_number_s']]
        self.assertGreater(len(set(values)), 1)
        self.assertTrue(all(pattern.match(value) is None for value in values))

    def test_each_rule_uses_the_shared_seeded_random_generator(self):
        for field in ('email_t', 'phone_t', 'ssn_t', 'part_number_s', 'notes_t'):
            first_rng = random.Random(42)
            second_rng = random.Random(42)
            first = [demo.malformed_value(field, 7, first_rng) for unused in range(24)]
            second = [demo.malformed_value(field, 7, second_rng) for unused in range(24)]
            self.assertEqual(first, second)
            self.assertGreater(len(set(first)), 1)

    def test_contact_fields_have_varied_values_that_fail_their_regexes(self):
        presets = definitions()
        for field, rule in [('email_t', 'email_base'), ('phone_t', 'us_phone_base'),
                            ('ssn_t', 'ssn_base')]:
            pattern = presets[rule]['rules'][0][2]
            rng = random.Random(42)
            values = set(demo.malformed_value(field, index, rng)
                         for index in range(24))
            self.assertGreaterEqual(len(values), 6)
            self.assertTrue(all(pattern.fullmatch(value) is None for value in values))
        rng = random.Random(42)
        self.assertNotIn('not-an-email', set(
            demo.malformed_value('email_t', index, rng) for index in range(24)))

    def test_other_text_fields_have_varied_detectable_unicode_defects(self):
        specialized = {'email_t', 'phone_t', 'ssn_t', 'part_number_s',
                       'event_date_dt'}
        for field in set(demo.FIELDS) - specialized:
            rng = random.Random(42)
            values = set(demo.malformed_value(field, 7, rng)
                         for unused in range(24))
            self.assertEqual(len(values), 6)
            self.assertTrue(all(code_point_failure_reason(value) for value in values))

    def test_future_dates_are_varied_valid_date_strings(self):
        values = set(demo.invalid_date(7, sequence)
                     for sequence in range(4))
        self.assertEqual(len(values), 4)
        self.assertTrue(all(value.endswith('Z') and 'T' in value for value in values))

    def test_text_errors_include_named_whitespace_examples(self):
        docs, _ = demo.generate(60, incorrect_percent=100, seed=42)
        values = set(doc.get('first_name_t') for doc in docs)
        self.assertIn(' leading whitespace example', values)
        self.assertIn('trailing whitespace example ', values)
        self.assertIn(' leading and trailing whitespace example ', values)

    def test_format_fields_use_three_three_three_eleven_mix(self):
        docs, _ = demo.generate(100, incorrect_percent=20, seed=42)
        values = [doc.get('email_t', demo.MISSING) for doc in docs]
        self.assertEqual(sum(value is None for value in values), 3)
        self.assertNotIn(demo.MISSING, values)
        self.assertEqual(sum(value in ('', ' \t\n') for value in values), 3)
        whitespace = (' leading whitespace example', 'trailing whitespace example ',
                      ' leading and trailing whitespace example ')
        self.assertEqual(sum(value in whitespace for value in values), 3)
        regex = definitions()['email_base']['rules'][0][2]
        self.assertEqual(sum(isinstance(value, str) and value not in whitespace
                             and value not in ('', ' \t\n')
                             and regex.fullmatch(value) is None for value in values), 11)

    def test_standard_text_keeps_unicode_corruption_rare(self):
        docs, _ = demo.generate(1000, incorrect_percent=20, seed=42)
        values = [doc.get('first_name_t') for doc in docs]
        self.assertEqual(sum(bool(code_point_failure_reason(value))
                             for value in values if isinstance(value, str)), 1)

    def test_per_field_option_is_not_supported(self):
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            demo.main(['--field_percent', 'email_t=25'])
        self.assertEqual(error.exception.code, 2)

    def test_no_arguments_show_help_without_generating(self):
        generate = Mock(side_effect=AssertionError('must not generate'))
        with patch('sys.stdout', io.StringIO()) as output, patch.dict(demo.main.__globals__, generate=generate):
            self.assertEqual(demo.main([]), 0)
        self.assertIn('usage: generate_test_data_solr.py', output.getvalue())
        self.assertIn('--rows', output.getvalue())
        self.assertIn('--size', output.getvalue())
        self.assertIn('Examples:', output.getvalue())
        self.assertNotIn('--incorrect-percent', output.getvalue())
        self.assertNotIn('--data-files-dir', output.getvalue())
        self.assertFalse(generate.called)


    def test_random_default_records_replayable_seed(self):
        random_source = Mock()
        random_source.getrandbits.side_effect = [123456, 789012]
        with patch.object(demo.random, 'SystemRandom', return_value=random_source):
            first = demo.generate(100)
            second = demo.generate(100)
        self.assertEqual(first[1], 123456)
        self.assertEqual(second[1], 789012)
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(first, demo.generate(100, seed=first[1]))
        for seed in (0, -1):
            self.assertEqual(demo.generate(100, seed=seed), demo.generate(100, seed=seed))


    def test_rows_required_when_generating(self):
        with patch('sys.stderr', io.StringIO()) as output, self.assertRaises(SystemExit) as error:
            demo.main(['--incorrect_percent', '20'])
        self.assertEqual(error.exception.code, 2)
        self.assertIn('--rows is required', output.getvalue())

    def test_rows_and_size_aliases(self):
        for option in ('--rows', '--size'):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                with patch('sys.stdout', io.StringIO()):
                    demo.main([option, '1_0', '--seed', '42', '--data_files_dir', directory])
                with open(os.path.join(directory, 'documents_solr.json')) as stream:
                    self.assertEqual(len(json.load(stream)), 10)
