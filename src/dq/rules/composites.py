"""Load predefined composite rules and expand them to ordered base rules."""
from collections import OrderedDict
import configparser
import os
import re

from dq.errors import ReportError
from dq.rules.metadata import read_metadata


RULES_DIRECTORY = os.path.dirname(__file__)


def _load_composites():
    """Load directory-named composite rules from their INI files."""
    result = OrderedDict()
    for name in sorted(os.listdir(RULES_DIRECTORY)):
        if not name.endswith('_composite'):
            continue
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            raise ReportError('invalid composite rule directory: ' + name)
        path = os.path.join(RULES_DIRECTORY, name, 'rule.ini')
        if not os.path.isfile(path):
            raise ReportError('{0} composite rule must contain rule.ini'.format(name))
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with open(path, encoding='utf-8') as stream:
                parser.read_file(stream)
            if parser.has_section('base_rule'):
                raise ValueError('_composite directory cannot contain [base_rule]')
            if not parser.has_section('composite_rule'):
                raise ValueError('expected a [composite_rule] section')
            metadata = read_metadata(parser)
            values = dict(parser.items('composite_rule'))
            unknown = set(values) - {'rules'}
            if unknown:
                raise ValueError('unknown composite rule setting: ' +
                                 ', '.join(sorted(unknown)))
            rules = tuple(item for item in re.split(r'[\s,]+', values.get('rules', '').strip())
                          if item)
            if not rules:
                raise ValueError('at least one component rule is required')
            if any(not re.match(r'^[a-z][a-z0-9_]*_(base|composite)$', item)
                   for item in rules):
                raise ValueError('component names must end in _base or _composite')
        except (OSError, configparser.Error, ValueError) as error:
            raise ReportError('invalid composite rule INI file {0}: {1}'.format(
                path, error)) from error
        result[name] = dict(metadata, rules=rules, path=path)
    return result


COMPOSITES = _load_composites()


def expand(names, base_names):
    """Flatten nested composites, preserving order and evaluating each base once."""
    base_names = set(base_names)
    flattened = []
    seen = set()

    def visit(name, stack):
        if name in COMPOSITES:
            if name in stack:
                cycle = stack[stack.index(name):] + [name]
                raise ReportError('composite rule cycle: ' + ' -> '.join(cycle))
            for child in COMPOSITES[name]['rules']:
                visit(child, stack + [name])
            return
        if name not in base_names:
            raise ReportError('unknown rule: ' + name)
        if name not in seen:
            seen.add(name)
            flattened.append(name)

    for name in names:
        visit(name, [])
    return flattened
