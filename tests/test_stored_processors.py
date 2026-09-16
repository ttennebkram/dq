"""Stored-value processors and portable user regex definitions."""
import configparser
import csv
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.config import write_config
from dq.arguments import build_parser
from dq.main import main
from dq.errors import ReportError
from dq.rules.regex.definitions import read_definition, definitions
from dq.rules.regex.engine import handler
from dq.rules._text.processor import reasons
from dq.reports.date_checker.processor import parse_date
from dq.reports.date_checker.report import write_report
from dq import stored


class ProcessorTests(unittest.TestCase):
    def definition(self, directory, contents):
        path = os.path.join(directory, 'custom.ini')
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(contents)
        for section in parser.sections():
            if parser.has_option(section, 'regex_file'):
                filename = section.replace(':', '_') + '.regex'
                with open(os.path.join(directory, filename), 'w') as stream:
                    stream.write(parser.get(section, 'regex_file'))
                parser.set(section, 'regex_file', filename)
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
            config_path = os.path.join(directory, 'rule.ini')
            with open(config_path, 'w') as stream:
                stream.write('[rule]\nreport = no_match\n'
                             '[regex:regex01]\nregex_file = patterns/literal.regex\n'
                             'case_sensitive = false\nregex_format = compact\n')
            definition = read_definition(config_path)
            expression = definition['rules'][0][2]
            self.assertEqual(expression.pattern, pattern)
            self.assertIsNotNone(expression.fullmatch('abc # literal\n'))
            self.assertIsNone(expression.fullmatch('abc # literal'))
            self.assertEqual(definition['pattern_paths'][0][1], pattern_path)
            os.unlink(pattern_path)
            with self.assertRaises(ReportError) as error:
                read_definition(config_path)
            self.assertIn(pattern_path, str(error.exception))
            self.assertIn('regex:regex01', str(error.exception))

    def test_regex_files_are_alternatives(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename, pattern in [('letters.regex', '[a-z]+'), ('digits.regex', '[0-9]+')]:
                with open(os.path.join(directory, filename), 'w') as stream:
                    stream.write(pattern)
            path = os.path.join(directory, 'alternatives.ini')
            with open(path, 'w') as stream:
                stream.write('[rule]\nreport = no_match\n'
                             '[regex:regex01]\nregex_file = letters.regex\nregex_format = compact\n'
                             '[regex:regex02]\nregex_file = digits.regex\nregex_format = compact\n')
            definition = read_definition(path)
            self.assertEqual(len(definition['pattern_paths']), 2)
            source = [('1', 'f', 'abc'), ('2', 'f', '123'), ('3', 'f', '---')]
            for report, expected in [('no_match', ['3']), ('match', ['1', '2'])]:
                definition['report'] = report
                with patch('dq.stored.fields', return_value=[{'name':'f'}]), patch('dq.stored.values', return_value=iter(source)):
                    _, pages = handler(definition, 'csv')('url')
                    rows = [row for page in pages for row in page]
                self.assertEqual([row[0] for row in rows], expected)
            os.unlink(os.path.join(directory, 'digits.regex'))
            with self.assertRaises(ReportError):
                read_definition(path)

    def test_regex_modes_flags_and_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            definition = self.definition(directory, '''[rule]
report = no_match
[regex:regex01]
regex_file = abc [0-9]+
case_sensitive = false
''')
            source = [('1', 'f', 'ABC12'), ('2', 'f', 'xxx,"value\r\n'), ('3','f','')]
            with patch('dq.stored.fields', return_value=[{'name':'f'}]), patch('dq.stored.values', return_value=iter(source)):
                headers, pages = handler(definition, 'csv')('url')
                rows = [r for page in pages for r in page]
            self.assertEqual(headers, ['id', 'reason', 'value'])
            self.assertEqual(len(rows), 2)
            self.assertTrue(all('no configured regex matched' in row[1] for row in rows))
            definition['report'] = 'match'
            with patch('dq.stored.fields', return_value=[{'name':'f'}]), patch('dq.stored.values', return_value=iter(source[:1])):
                _, pages = handler(definition, 'csv')('url')
                self.assertEqual(len(list(pages)[0]), 1)

    def test_regex_blank_values_for_both_match_meanings(self):
        from dq.rules.regex.engine import findings
        import re
        source = [('null', 'f', None), ('empty', 'f', ''), ('space', 'f', ' '),
                  ('tabs', 'f', '\t\r\n'), ('unicode', 'f', '\u00a0\u2003'),
                  ('zero', 'f', 0), ('false', 'f', False)]
        definition = {'name': 'check', 'rules': [
            ('regex01', 'full', re.compile(r'[\s\S]*')),
            ('regex02', 'full', re.compile(r'[\s\S]*'))]}
        for report in ('no_match', 'match'):
            definition['report'] = report
            with patch('dq.stored.values', return_value=iter(source)):
                rows = list(findings(definition, 'url', []))
            ids = [row[0] for row in rows]
            self.assertEqual(ids, [item[0] for item in source] if report == 'match' else [])
            if report == 'match':
                self.assertTrue(all(row[1].startswith('check: regex regex01 matched') for row in rows))
                self.assertEqual([row[2] for row in rows[:5]], ['', '', ' ', '\t\r\n', '\u00a0\u2003'])

    def test_invalid_regex_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ReportError):
                self.definition(directory, '[rule]\nname = custom\nreport = no_match\n'
                                '[regex:regex01]\nregex_file = a')
            with self.assertRaises(ReportError):
                self.definition(directory, '[rule]\n'
                                '[regex:regex01]\nregex_file = a')
            for rule in ['regex_file = [', 'regex_file = a\ncase_sensitive = maybe',
                         'regex_file = a\nregex_format = wide',
                         'regex_file = a\nmatch_mode = search']:
                with self.assertRaises(ReportError):
                    self.definition(directory, '[rule]\nreport = no_match\n'
                                    '[regex:regex01]\n' + rule)

    def test_case_sensitive_multiline_and_literal_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            definition = self.definition(directory, '''[rule]
report = no_match
[regex:regex01]
regex_file = ^Abc[ ]\\#\ncase_sensitive = true
multiline = true
match_mode = partial
''')
            expression = definition['rules'][0][2]
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

    def test_external_custom_rules_directory_is_not_discovered_in_mvp(self):
        with tempfile.TemporaryDirectory() as directory:
            custom_rules = os.path.join(directory, 'custom_rules')
            os.mkdir(custom_rules)
            self.definition(custom_rules, '[rule]\nreport = no_match\n'
                            '[regex:regex01]\nregex_file = valid')
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://solr/c', None)
            with patch('sys.stderr', io.StringIO()) as err, self.assertRaises(SystemExit):
                main(['--config', path, '--rule', 'custom', '--reports_dir', directory])
            self.assertIn('unknown rule: custom', err.getvalue())
            self.assertFalse(os.path.exists(os.path.join(directory, 'f_custom.csv')))

    def test_invalid_matches_are_labeled_as_offending(self):
        with tempfile.TemporaryDirectory() as directory:
            definition = self.definition(directory, '[rule]\nreport=match\n'
                                         '[regex:regex01]\nregex_file=valid')
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://solr/c', None, reports_dir=directory)
            source = [('1', 'f', 'valid'), ('2', 'f', 'invalid')]
            with patch('dq.actions.load_handler', return_value=handler(definition, 'csv')), \
                    patch('dq.stored.fields', return_value=[{'name': 'f'}]), \
                    patch('dq.stored.values', return_value=iter(source)), \
                    patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()) as err:
                self.assertEqual(main(['--config', path, '--rule', 'custom']), 0)
            with open(os.path.join(directory, 'f_custom.csv'), newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][0], '1')
            self.assertIn('Offending records exported: 1', err.getvalue())

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
