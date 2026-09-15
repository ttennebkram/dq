"""Stored-value processors and portable user regex definitions."""
import configparser
import csv
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.config import load_config, write_config
from dq.arguments import build_parser
from dq.main import main
from dq.processors import ReportError
from dq.processors.regex.definitions import read_definition, definitions
from dq.processors.regex.engine import handler
from dq.processors.standard_text.processor import reasons
from dq.processors.date_checker.processor import parse_date
from dq.reports.date_checker import write_report
from dq.settings import processor_directory
from dq import stored


class ProcessorTests(unittest.TestCase):
    def definition(self, directory, contents):
        path = os.path.join(directory, 'custom.ini')
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(contents)
        for section in parser.sections():
            for key in ('must_match', 'must_not_match'):
                if parser.has_option(section, key):
                    filename = section.replace(':', '_') + '_' + key + '.regex'
                    with open(os.path.join(directory, filename), 'w') as stream:
                        stream.write(parser.get(section, key))
                    parser.set(section, key, filename)
        with open(path, 'w') as stream:
            parser.write(stream)
        return read_definition(path)

    def test_raw_pattern_paths_relative_to_ini_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            os.mkdir(os.path.join(directory, 'patterns'))
            pattern_path = os.path.join(directory, 'patterns', 'literal.regex')
            pattern = 'Abc # literal\n'
            with open(pattern_path, 'w', newline='') as stream:
                stream.write(pattern)
            config_path = os.path.join(directory, 'processor.ini')
            with open(config_path, 'w') as stream:
                stream.write('[processor]\nname = literal\nverbose = false\n'
                             '[rule:literal]\nmust_match = patterns/literal.regex\n')
            definition = read_definition(config_path)
            expression = definition['rules'][0][3][0]
            self.assertEqual(expression.pattern, pattern)
            self.assertIsNotNone(expression.fullmatch('abc # literal\n'))
            self.assertIsNone(expression.fullmatch('abc # literal'))
            self.assertEqual(definition['pattern_paths'][0][1], pattern_path)
            os.unlink(pattern_path)
            with self.assertRaises(ReportError) as error:
                read_definition(config_path)
            self.assertIn(pattern_path, str(error.exception))
            self.assertIn('rule:literal', str(error.exception))

    def test_must_match_files_are_or_with_one_finding_per_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename, pattern in [('letters.regex', '[a-z]+'), ('digits.regex', '[0-9]+')]:
                with open(os.path.join(directory, filename), 'w') as stream:
                    stream.write(pattern)
            path = os.path.join(directory, 'alternatives.ini')
            with open(path, 'w') as stream:
                stream.write('[processor]\nname = alternatives\n[rule:format]\n'
                             'must_match = letters.regex\n    digits.regex\n')
            definition = read_definition(path)
            self.assertEqual(len(definition['pattern_paths']), 2)
            source = [('1', 'f', 'ABC'), ('2', 'f', '123'), ('3', 'f', '---')]
            for result, expected in [('failed', ['3']), ('succeeded', ['1', '2'])]:
                definition['results'] = result
                with patch('dq.stored.fields', return_value=[{'name':'f'}]), patch('dq.stored.values', return_value=iter(source)):
                    _, pages = handler(definition, 'csv')('url')
                    rows = [row for page in pages for row in page]
                self.assertEqual([row[0] for row in rows], expected)
            os.unlink(os.path.join(directory, 'digits.regex'))
            with self.assertRaises(ReportError):
                read_definition(path)

    def test_regex_modes_flags_and_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            definition = self.definition(directory, '''[processor]
name = custom
[rule:format]
must_match =
    abc  # ignore case by default
    [0-9]+
[rule:forbidden]
must_not_match = xxx
match_mode = search
''')
            source = [('1', 'f', 'ABC12'), ('2', 'f', 'xxx,"value\r\n'), ('3','f','')]
            with patch('dq.stored.fields', return_value=[{'name':'f'}]), patch('dq.stored.values', return_value=iter(source)):
                headers, pages = handler(definition, 'csv')('url')
                rows = [r for page in pages for r in page]
            self.assertEqual(headers, ['id', 'reason', 'value'])
            self.assertEqual(len(rows), 2)
            self.assertIn('surrounding_whitespace', rows[0][1])
            self.assertIn('empty_values: empty string', rows[1][1])
            definition['results'] = 'succeeded'
            with patch('dq.stored.fields', return_value=[{'name':'f'}]), patch('dq.stored.values', return_value=iter(source[:1])):
                _, pages = handler(definition, 'csv')('url')
                self.assertEqual(len(list(pages)[0]), 1)

    def test_regex_blank_failures_for_both_result_modes(self):
        from dq.processors.regex.engine import findings
        import re
        source = [('null', 'f', None), ('empty', 'f', ''), ('space', 'f', ' '),
                  ('tabs', 'f', '\t\r\n'), ('unicode', 'f', '\u00a0\u2003'),
                  ('zero', 'f', 0), ('false', 'f', False)]
        for kind in ('must_match', 'must_not_match'):
            definition = {'name': 'check', 'rules': [
                ('anything', kind, 'full', [re.compile('.*')]),
                ('second', kind, 'full', [re.compile('.*')])]}
            for result in ('failed', 'succeeded'):
                definition['results'] = result
                with patch('dq.stored.values', return_value=iter(source)):
                    rows = list(findings(definition, 'url', []))
                ids = [row[0] for row in rows]
                blanks = ['null', 'empty', 'space', 'tabs', 'unicode'] if result == 'failed' else []
                succeeds = kind == 'must_match'
                self.assertEqual(ids, blanks + (['zero', 'false']
                    if succeeds == (result == 'succeeded') else []))
                if result == 'failed':
                    self.assertEqual([row[1] for row in rows[:5]],
                        ['check: empty_values: null', 'check: empty_values: empty string'] + ['check: empty_values: whitespace only'] * 3)
                    self.assertEqual([row[2] for row in rows[:5]], ['', '', ' ', '\t\r\n', '\u00a0\u2003'])

    def test_invalid_regex_and_duplicate_processors(self):
        with tempfile.TemporaryDirectory() as directory:
            for rule in ['must_match = [', 'must_match = a\nmust_not_match = b', 'must_match = a\ncase_sensitive = maybe']:
                with self.assertRaises(ReportError):
                    self.definition(directory, '[processor]\nname = custom\n[rule:x]\n' + rule)
            self.definition(directory, '[processor]\nname = us_phone\n[rule:x]\nmust_match = a')
            with self.assertRaises(ReportError):
                definitions(directory)

    def test_case_sensitive_multiline_and_literal_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            definition = self.definition(directory, '''[processor]
name = custom
case_sensitive = true
multiline = true
[rule:line]
must_match = ^Abc[ ]\\#\nmatch_mode = search
''')
            expression = definition['rules'][0][3][0]
            self.assertIsNotNone(expression.search('first\nAbc #'))
            self.assertIsNone(expression.search('first\nabc #'))

    def test_unicode_indicators(self):
        self.assertEqual(reasons('café 日本語\n\t'), [])
        self.assertEqual(len(reasons('\ufffd\ufffd\x00')), 2)
        self.assertTrue(reasons('\u200b'))

    def test_dates_and_histogram(self):
        self.assertEqual(parse_date('2024-01-01T01:00:00+01:00').isoformat(), '2024-01-01T00:00:00')
        with self.assertRaises(ValueError):
            parse_date('2023-02-29')
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'date_checker.md')
            data = [('1','created','2024-01-01'), ('2','created','2024-02-01'),
                    ('3','created','bad'), ('4','created','2999-01-01')]
            with patch('dq.stored.fields', return_value=[{'name':'created','type':'pdate'}]), patch('dq.stored.values', return_value=iter(data)):
                paths = write_report('url', path)
            with open(paths[0]) as stream:
                report = stream.read()
            self.assertIn('created_date_checker_dates.svg', report)
            self.assertIn('Invalid values', report)
            with open(os.path.join(directory, 'created_date_checker_dates.svg')) as stream:
                svg = stream.read()
            self.assertIn('<svg', svg)
            self.assertLessEqual(svg.count('<rect'), 61)

    def test_user_directory_ini_write_and_cli_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            processors = os.path.join(directory, 'processors')
            os.mkdir(processors)
            self.definition(processors, '[processor]\nname = custom\n[rule:x]\nmust_match = valid')
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://solr/c', None)
            config = load_config(path)
            self.assertEqual(processor_directory(config), os.path.realpath(processors))
            source = [('1','f','bad,"text\r\n')]
            with patch('dq.stored.fields', return_value=[{'name':'f'}]), patch('dq.stored.values', return_value=iter(source)), patch('sys.stdout',io.StringIO()) as out, patch('sys.stderr',io.StringIO()):
                self.assertEqual(main(['--config',path,'--rule','custom','--action','csv','--reports_dir',directory]), 0)
            self.assertIn('f_custom.csv', out.getvalue())
            self.assertNotIn(source[0][2], out.getvalue())
            with open(os.path.join(directory, 'f_custom.csv'), encoding='utf-8', newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows[0], ['id','reason','value'])
            self.assertEqual(rows[1][2], source[0][2])

    def test_successful_regex_exports_are_labeled_as_passing(self):
        with tempfile.TemporaryDirectory() as directory:
            processors = os.path.join(directory, 'processors')
            os.mkdir(processors)
            self.definition(processors, '[processor]\nname=custom\nresults=succeeded\n[rule:x]\nmust_match=valid')
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://solr/c', None, reports_dir=directory)
            source = [('1', 'f', 'valid'), ('2', 'f', 'invalid')]
            with patch('dq.stored.fields', return_value=[{'name': 'f'}]), \
                    patch('dq.stored.values', return_value=iter(source)), \
                    patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()) as err:
                self.assertEqual(main(['--config', path, '--rule', 'custom', '--action', 'csv']), 0)
            with open(os.path.join(directory, 'f_custom.csv'), newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][0], '1')
            self.assertIn('Passing records exported: 1', err.getvalue())
            self.assertNotIn('Offending records exported', err.getvalue())

    def test_stored_paging_aliases_multivalues_and_partial_rejection(self):
        responses = [{'uniqueKey':'key_s'}, {'response':{'docs':[{'dq_key':'a','dq_value0':['x',None,'y']}]},'nextCursorMark':'next'}, {'response':{'docs':[]},'nextCursorMark':'next'}]
        with patch('dq.stored.get_json', side_effect=responses) as get:
            data = stored.values('url',[{'name':'text_s'}])
            self.assertFalse(get.called)
            self.assertEqual(list(data), [('a','text_s','x'),('a','text_s','y')])
            self.assertEqual(get.call_args_list[1][1]['fl'], 'dq_key:key_s,dq_value0:text_s')
        with patch('dq.stored.get_json', side_effect=[{'uniqueKey':'id'}, {'responseHeader':{'partialResults':True}}]):
            with self.assertRaises(stored.SolrError):
                list(stored.values('url',[{'name':'text_s'}]))
