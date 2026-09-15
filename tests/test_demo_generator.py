"""Reproducible per-field defect rates and boundary validation."""
import runpy
from types import SimpleNamespace
import os
import io
from unittest.mock import Mock, patch
import unittest

path = os.path.join(os.path.dirname(__file__), '..', 'generate-test-collection', 'test_data.py')
demo = SimpleNamespace(**runpy.run_path(path))


class DemoGeneratorTests(unittest.TestCase):
    def test_exact_percent_per_field_and_reproducibility(self):
        docs, expected = demo.generate(100, seed=42)
        self.assertEqual((docs, expected), demo.generate(100, seed=42))
        for field in demo.FIELDS:
            errors = [r for r in expected['injected_errors'] if r['field'] == field]
            self.assertEqual(len(errors), 20)
            self.assertEqual(len(set(r['id'] for r in errors)), 20)
            if field == 'event_date_dt':
                self.assertEqual(set(r['kind'] for r in errors), {'missing','null','future date'})
                continue
            for kind in ('missing', 'null', 'empty string', 'whitespace only', 'malformed'):
                self.assertEqual(sum(r['kind'] == kind for r in errors), 4)

    def test_global_percentage_rounding_and_limits(self):
        _, result = demo.generate(10, 25)
        for field in demo.FIELDS:
            self.assertEqual(result['fields'][field]['incorrect_documents'], 3)
        for kwargs in ({'count':0}, {'incorrect_percent':101}, {'incorrect_percent':float('nan')}):
            with self.assertRaises(ValueError):
                demo.generate(**dict({'count':100}, **kwargs))

    def test_per_field_option_is_not_supported(self):
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as error:
            demo.main(['--field_percent', 'email_t=25'])
        self.assertEqual(error.exception.code, 2)

    def test_no_arguments_show_help_without_generating(self):
        generate = Mock(side_effect=AssertionError('must not generate'))
        with patch('sys.stdout', io.StringIO()) as output, patch.dict(demo.main.__globals__, generate=generate):
            self.assertEqual(demo.main([]), 0)
        self.assertIn('usage: generate-test-data-solr.py', output.getvalue())
        self.assertIn('--count', output.getvalue())
        self.assertIn('Examples:', output.getvalue())
        self.assertFalse(generate.called)


    def test_random_default_records_replayable_seed(self):
        random_source = Mock()
        random_source.getrandbits.side_effect = [123456, 789012]
        with patch.object(demo.random, 'SystemRandom', return_value=random_source):
            first = demo.generate(100)
            second = demo.generate(100)
        self.assertEqual(first[1]['seed'], 123456)
        self.assertEqual(second[1]['seed'], 789012)
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(first, demo.generate(100, seed=first[1]['seed']))
        for seed in (0, -1):
            self.assertEqual(demo.generate(100, seed=seed), demo.generate(100, seed=seed))


    def test_count_required_when_generating(self):
        with patch('sys.stderr', io.StringIO()) as output, self.assertRaises(SystemExit) as error:
            demo.main(['--incorrect_percent', '20'])
        self.assertEqual(error.exception.code, 2)
        self.assertIn('--count', output.getvalue())
