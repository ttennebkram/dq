"""Read named regex checks from INI files referencing separate .regex files."""
import configparser
import os
import re
from dq.errors import ReportError
from dq.rules.metadata import read_metadata


def _builtin_paths():
    rules_directory = os.path.dirname(os.path.dirname(__file__))
    paths = []
    for name in sorted(os.listdir(rules_directory)):
        directory = os.path.join(rules_directory, name)
        if name.endswith('_base') and os.path.isdir(directory):
            path = os.path.join(directory, 'rule.ini')
            if os.path.isfile(path):
                paths.append(path)
    return paths


def read_definition(path, allow_unrelated=False):
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=None)
    try:
        with open(path, encoding='utf-8') as stream:
            parser.read_file(stream)
        if allow_unrelated and not parser.has_section('base_rule'):
            if parser.has_section('composite_rule'):
                raise ValueError('_base directory cannot contain [composite_rule]')
            return None
        if not parser.has_section('base_rule'):
            raise ValueError('expected a [base_rule] section')
        if parser.has_section('composite_rule'):
            raise ValueError('_base directory cannot contain [composite_rule]')
        metadata = read_metadata(parser)
        regex_sections = [section for section in parser.sections()
                          if section.startswith('regex:')]
        if allow_unrelated and not regex_sections:
            return None
        defaults = dict(parser.items('base_rule'))
        name = os.path.basename(os.path.dirname(os.path.abspath(path)))
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            raise ValueError('rule directory name must use lowercase letters, digits, and underscores')
        allowed = {'report'}
        if set(defaults) - allowed:
            raise ValueError('unknown rule setting: ' + ', '.join(sorted(set(defaults) - allowed)))
        report = defaults.get('report')
        if report not in ('match', 'no_match'):
            raise ValueError('report is required and must be match or no_match')
        rules = []
        pattern_paths = []
        for section in parser.sections():
            if section in ('rule', 'base_rule'):
                continue
            if not re.match(r'^regex:regex[0-9]{2}$', section):
                raise ValueError('expected a numbered [regex:regex01] section')
            check_name = section[6:].strip()
            values = dict(parser.items(section))
            if set(values) - {'regex_file', 'match_mode', 'case_sensitive', 'regex_format', 'multiline'}:
                raise ValueError('unknown setting in ' + section)
            filename = values.get('regex_file', '').strip()
            if len(filename.splitlines()) != 1 or not filename.endswith('.regex'):
                raise ValueError(section + ' must specify one regex_file ending in .regex')
            flags = 0
            case_sensitive = values.get('case_sensitive', 'true').lower()
            if case_sensitive not in ('true', 'false'):
                raise ValueError('case_sensitive must be true or false')
            if case_sensitive == 'false':
                flags |= re.I
            regex_format = values.get('regex_format', 'verbose').lower()
            if regex_format not in ('verbose', 'compact'):
                raise ValueError('regex_format must be verbose or compact')
            if regex_format == 'verbose':
                flags |= re.X
            multiline = values.get('multiline', 'false').lower()
            if multiline not in ('true', 'false'):
                raise ValueError('multiline must be true or false')
            if multiline == 'true':
                flags |= re.M
            mode = values.get('match_mode', 'full')
            if mode not in ('full', 'partial'):
                raise ValueError('match_mode must be full or partial')
            pattern_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(path)), filename))
            try:
                with open(pattern_path, encoding='utf-8', newline='') as stream:
                    pattern = stream.read()
                expression = re.compile(pattern, flags)
            except (OSError, UnicodeError, re.error) as error:
                raise ValueError('{0}: cannot load regex {1}: {2}'.format(section, pattern_path, error))
            pattern_paths.append((check_name, pattern_path))
            rules.append((check_name, mode, expression))
        if not rules:
            raise ValueError('at least one numbered [regex:regex01] section is required')
        if len(set(rule[0] for rule in rules)) != len(rules):
            raise ValueError('duplicate regex check name')
        return dict(metadata, name=name, rule_type='base', report=report,
                    rules=rules, pattern_paths=pattern_paths,
                    path=os.path.abspath(path))
    except (OSError, configparser.Error, ValueError, re.error) as error:
        raise ReportError('invalid rule INI file {0}: {1}'.format(path, error)) from error


def definitions():
    paths = _builtin_paths()
    result = {}
    for path in paths:
        item = read_definition(path, allow_unrelated=True)
        if item is None:
            continue
        if item['name'] in result:
            raise ReportError('duplicate regex rule name: ' + item['name'])
        result[item['name']] = item
    return result
