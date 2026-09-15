"""Read named regex rules from INI files referencing separate .regex pattern files."""
import configparser
import os
import re
from dq.processors import ReportError


def read_definition(path, allow_unrelated=False):
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=None)
    try:
        with open(path, encoding='utf-8') as stream:
            parser.read_file(stream)
        if allow_unrelated and not parser.has_section('processor'):
            return None
        defaults = dict(parser.items('processor'))
        name = defaults.get('name', os.path.splitext(os.path.basename(path))[0])
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            raise ValueError('processor name must use lowercase letters, digits, and underscores')
        allowed = {'name', 'description', 'case_sensitive', 'verbose', 'multiline', 'results'}
        if set(defaults) - allowed:
            raise ValueError('unknown processor setting: ' + ', '.join(sorted(set(defaults) - allowed)))
        results = defaults.get('results', 'failed')
        if results not in ('failed', 'succeeded'):
            raise ValueError('results must be failed or succeeded')
        rules = []
        pattern_paths = []
        for section in parser.sections():
            if section == 'processor':
                continue
            if not section.startswith('rule:') or not section[5:].strip():
                raise ValueError('expected a named [rule:name] section')
            values = dict(parser.items(section))
            if set(values) - {'must_match', 'must_not_match', 'match_mode', 'case_sensitive', 'verbose', 'multiline'}:
                raise ValueError('unknown setting in ' + section)
            kinds = [kind for kind in ('must_match', 'must_not_match') if kind in values]
            if len(kinds) != 1:
                raise ValueError(section + ' must specify exactly one of must_match or must_not_match')
            flags = 0
            for setting, default, flag, invert in [('case_sensitive', 'false', re.I, True),
                                                  ('verbose', 'true', re.X, False),
                                                  ('multiline', 'false', re.M, False)]:
                boolean = values.get(setting, defaults.get(setting, default)).lower()
                if boolean not in ('true', 'false'):
                    raise ValueError(setting + ' must be true or false')
                if (boolean == 'true') != invert:
                    flags |= flag
            mode = values.get('match_mode', 'full')
            if mode not in ('full', 'search'):
                raise ValueError('match_mode must be full or search')
            filenames = [line.strip() for line in values[kinds[0]].splitlines() if line.strip()]
            if not filenames or any(not name.endswith('.regex') for name in filenames):
                raise ValueError(section + ' must reference .regex filenames, one per line')
            if kinds[0] == 'must_not_match' and len(filenames) != 1:
                raise ValueError(section + ' must_not_match accepts one regex file per rule')
            expressions = []
            for filename in filenames:
                pattern_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(path)), filename))
                try:
                    with open(pattern_path, encoding='utf-8', newline='') as stream:
                        pattern = stream.read()
                    expressions.append(re.compile(pattern, flags))
                except (OSError, UnicodeError, re.error) as error:
                    raise ValueError('{0}: cannot load regex {1}: {2}'.format(section, pattern_path, error))
                pattern_paths.append((section[5:].strip(), pattern_path))
            rules.append((section[5:].strip(), kinds[0], mode, expressions))
        if not rules:
            raise ValueError('at least one [rule:name] is required')
        if len(set(rule[0] for rule in rules)) != len(rules):
            raise ValueError('duplicate regex rule name')
        return {'name': name, 'description': defaults.get('description', name),
                'rule_type': 'base', 'results': results, 'rules': rules,
                'pattern_paths': pattern_paths, 'path': os.path.abspath(path)}
    except (OSError, configparser.Error, ValueError, re.error) as error:
        raise ReportError('invalid processor INI file {0}: {1}'.format(path, error)) from error


def definitions(directory=None):
    directories = [os.path.join(os.path.dirname(__file__), 'presets')]
    if directory:
        if not os.path.isdir(directory):
            raise ReportError('processor directory does not exist: ' + directory)
        directories.append(directory)
    result = {}
    for folder in directories:
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith('.ini'):
                continue
            item = read_definition(os.path.join(folder, filename), allow_unrelated=True)
            if item is None:
                continue
            if item['name'] in result:
                raise ReportError('duplicate regex processor name: ' + item['name'])
            result[item['name']] = item
    return result
