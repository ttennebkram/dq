"""Discover rules and reports and lazily load their handlers."""
import importlib
import configparser
import os
import pkgutil
import re
import dq.reports
import dq.rules
from dq.errors import ReportError
from dq.rules.composites import COMPOSITES, expand
from dq.rules.metadata import read_metadata


# Deferred names are recognized for clear errors but stay out of catalogs.
PLANNED = (
    ('term_stats', 'analyze indexed terms and token lengths'),
    ('date_checker', 'date analysis and distribution graphs (after MVP)'),
)


def _packages(package):
    return sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item[1])


def discover_rules():
    """Inspect rule packages under dq.rules, never working-directory scripts."""
    entries = {}
    for finder, name, is_package in _packages(dq.rules):
        if not is_package or name.startswith('_'):
            continue
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            raise ReportError('invalid internal rule package: {0}'.format(name))
        if name.endswith('_composite'):
            if name not in COMPOSITES:
                raise ReportError('{0} composite rule must contain valid rule.ini'.format(name))
            continue
        if not name.endswith('_base'):
            continue
        path = os.path.join(finder.path, name, 'rule.ini')
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with open(path, encoding='utf-8') as stream:
                parser.read_file(stream)
            if not parser.has_section('base_rule'):
                raise ValueError('expected a [base_rule] section')
            if parser.has_section('composite_rule'):
                raise ValueError('_base directory cannot contain [composite_rule]')
            metadata = read_metadata(parser)
        except (OSError, configparser.Error, ValueError) as error:
            raise ReportError('invalid base rule INI file {0}: {1}'.format(path, error)) from error
        # INI-defined regex rules are cataloged by regex.definitions.
        if any(section.startswith('regex:') for section in parser.sections()):
            continue
        entries[name] = dict(metadata, csv=True, rule_type='base')
    return entries


def discover_reports():
    """Inspect report packages under dq.reports."""
    entries = {}
    for _, name, is_package in _packages(dq.reports):
        if not is_package or name.startswith('_'):
            continue
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            raise ReportError('invalid internal report package: {0}'.format(name))
        module = importlib.import_module('dq.reports.' + name)
        description = getattr(module, 'DESCRIPTION', None)
        if description is None:
            continue
        entries[name] = {'description': description,
                         'report': getattr(module, 'REPORT', None)}
    return entries


def discover():
    """Return the combined internal catalog for compatibility with older callers."""
    entries = {}
    for name, entry in discover_rules().items():
        entries[name] = {'description': entry['description'], 'report': None,
                         'csv': entry['csv'], 'rule_type': entry['rule_type']}
    for name, entry in discover_reports().items():
        if name in entries:
            raise ReportError('duplicate internal rule/report name: ' + name)
        entries[name] = {'description': entry['description'], 'report': entry['report'],
                         'csv': None, 'rule_type': None}
    return entries


def report_names():
    return tuple(sorted(name for name, entry in discover_reports().items() if entry['report']))


def report_catalog():
    entries = discover_reports()
    return [(name, 'implemented', entries[name]['description'])
            for name in report_names()]


def csv_names():
    from dq.rules.regex.definitions import definitions
    entries = discover_rules()
    return tuple(sorted([name for name, entry in entries.items() if entry['csv']] +
                        list(definitions()) + list(COMPOSITES)))


def rule_catalog():
    entries = discover_rules()
    from dq.rules.regex.definitions import definitions
    regexes = definitions()
    rows = [(name, definition['rule_type'], definition['description'])
            for name, definition in regexes.items()]
    rows.extend((name, entry['rule_type'], entry['description'])
                for name, entry in entries.items() if entry['csv'])
    rows.extend((name, 'predefined composite', definition['description'])
                for name, definition in COMPOSITES.items())
    return sorted(rows)


def report_help():
    return '\n'.join('  {0:12}   {1} - {2}'.format(
        name, status.upper(), description)
        for name, status, description in report_catalog())


def load_handler(name, action):
    if action not in ('report', 'csv'):
        raise ReportError('unknown action: {0}'.format(action))
    rule_entries = discover_rules()
    report_entries = discover_reports()
    from dq.rules.regex.definitions import definitions
    regexes = definitions()
    public_rule_names = set(rule_entries) | set(COMPOSITES)
    duplicates = public_rule_names.intersection(regexes)
    if duplicates:
        raise ReportError('duplicate rule names: {0}'.format(', '.join(sorted(duplicates))))

    if action == 'report':
        if isinstance(name, (list, tuple)):
            raise ReportError('reports must be loaded one at a time')
        if name in public_rule_names or name in regexes:
            raise ReportError('{0} is a rule; use --rule {0}. For a report, use quick_checkup or full_checkup.'.format(name))
        if name not in report_entries:
            if name in dict(PLANNED):
                raise ReportError('report not implemented yet: {0}'.format(name))
            raise ReportError('unknown report: {0}'.format(name))
        path = report_entries[name]['report']
        if not path:
            raise ReportError('{0} is deferred beyond the MVP'.format(name))
        prefix = 'dq.reports.' + name + '.'
    else:
        names = list(name) if isinstance(name, (list, tuple)) else [name]
        if not names:
            raise ReportError('at least one rule is required for the CSV action')
        known_base = set(rule_name for rule_name, entry in rule_entries.items()
                         if entry['csv']) | set(regexes)
        for rule_name in names:
            if rule_name not in known_base and rule_name not in COMPOSITES:
                if rule_name in report_entries:
                    raise ReportError('{0} is a special report and does not support CSV; use --report {0}'.format(rule_name))
                raise ReportError('unknown rule: {0}'.format(rule_name))
        from dq.rules.chain import handler
        return handler(expand(names, known_base), regexes)

    try:
        module_name, function_name = path.split(':')
        if not module_name.startswith(prefix):
            raise ValueError('handler must belong to its matching rule or report package')
        handler = getattr(importlib.import_module(module_name), function_name)
        if not callable(handler):
            raise ValueError('handler is not callable')
        return handler
    except (ImportError, AttributeError, ValueError) as error:
        raise ReportError('could not load {0} {1} handler: {2}'.format(name, action, error)) from error


def rule_help():
    return '\n'.join('  {0:29} {1}'.format(name, description)
                     for name, rule_type, description in rule_catalog())
