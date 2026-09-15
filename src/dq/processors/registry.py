"""Discover internal report packages and lazily load their action handlers."""
import importlib
import pkgutil
import re
import dq.processors
from dq.processors import ReportError

# Planned names remain visible in help without pretending to have implementations.
PLANNED = (
    ('term_stats', 'analyze indexed terms and token lengths'),
    ('date_checker', 'date analysis and distribution graphs (after MVP)'),
)
RULE_TYPES = ('base', 'composite')


def discover():
    """Only inspect packages under dq.processors, never working-directory scripts."""
    entries = {}
    for _, name, is_package in sorted(pkgutil.iter_modules(dq.processors.__path__), key=lambda item: item[1]):
        if not is_package or name.startswith('_'):
            continue
        module = importlib.import_module('dq.processors.' + name)
        if getattr(module, 'NAME', None) != name or not re.match(r'^[a-z][a-z0-9_]*$', name):
            raise ReportError('invalid internal report package: {0}'.format(name))
        report = getattr(module, 'REPORT', None)
        csv = getattr(module, 'CSV', None)
        rule_type = getattr(module, 'RULE_TYPE', None)
        if csv and rule_type not in RULE_TYPES:
            raise ReportError('{0} CSV rule must declare RULE_TYPE as base or composite'.format(name))
        if not csv and rule_type is not None:
            raise ReportError('{0} declares RULE_TYPE without a CSV rule'.format(name))
        entries[name] = {'description': module.DESCRIPTION,
                         'report': report,
                         'csv': csv,
                         'rule_type': rule_type}
    return entries


def report_names():
    available = sorted(name for name, entry in discover().items() if entry['report'])
    return tuple(available + [name for name, _ in PLANNED if name not in available])


def report_catalog():
    entries = discover()
    planned = dict(PLANNED)
    rows = []
    for name in report_names():
        implemented = bool(entries.get(name, {}).get('report'))
        rows.append((name, 'implemented' if implemented else 'planned',
                     entries[name]['description'] if implemented else planned[name]))
    return rows


def csv_names():
    from dq.processors.regex.definitions import definitions
    return tuple(sorted([name for name, entry in discover().items() if entry['csv']] + list(definitions())))


def rule_catalog():
    entries = discover()
    from dq.processors.regex.definitions import definitions
    regexes = definitions()
    rows = [(name, definition['rule_type'], definition['description'])
            for name, definition in regexes.items()]
    rows.extend((name, entry['rule_type'], entry['description'])
                for name, entry in entries.items() if entry['csv'])
    return sorted(rows)


def report_help():
    return '\n'.join('  {0:12}   {1} - {2}'.format(
        name, status.upper(), description)
        for name, status, description in report_catalog())


def load_handler(name, action, processor_dir=None):
    if action not in ('report', 'csv'):
        raise ReportError('unknown action: {0}'.format(action))
    entries = discover()
    from dq.processors.regex.definitions import definitions
    regexes = definitions(processor_dir)
    duplicates = set(entries).intersection(regexes)
    if duplicates:
        raise ReportError('duplicate processor names: {0}'.format(', '.join(sorted(duplicates))))
    if action == 'csv' and isinstance(name, (list, tuple)):
        names = list(name)
        if not names:
            raise ReportError('at least one rule is required for the CSV action')
        if len(names) == 1:
            return load_handler(names[0], action, processor_dir)
        for rule_name in names:
            if rule_name not in entries and rule_name not in regexes:
                if rule_name in dict(PLANNED):
                    raise ReportError('rule not implemented yet: {0}'.format(rule_name))
                raise ReportError('unknown rule: {0}'.format(rule_name))
            if rule_name in entries and not entries[rule_name]['csv']:
                raise ReportError('{0} is a special report and does not support CSV; use --report {0}'.format(rule_name))
            if rule_name in regexes and regexes[rule_name]['results'] != 'failed':
                raise ReportError('{0} exports succeeded values and cannot be combined with failure rules'.format(rule_name))
        from dq.processors.chain import handler
        return handler(names, regexes)
    if name in regexes:
        from dq.processors.regex.engine import handler
        return handler(regexes[name], action)
    if name not in entries:
        if name in dict(PLANNED):
            raise ReportError('rule not implemented yet: {0}'.format(name))
        raise ReportError('unknown rule: {0}'.format(name))
    if name in dict(PLANNED) and not (entries[name]['report'] or entries[name]['csv']):
        raise ReportError('{0} is deferred beyond the MVP'.format(name))
    path = entries[name][action]
    if not path:
        if action == 'report':
            raise ReportError('{0} is a rule; use --rule {0} --action csv. For a report, use quick_checkup or full_checkup.'.format(name))
        raise ReportError('{0} is a special report and does not support CSV; use --report {0}'.format(name))
    try:
        module_name, function_name = path.split(':')
        if not (module_name.startswith('dq.processors.' + name + '.') or
                (action == 'report' and module_name == 'dq.reports.' + name)):
            raise ValueError('handler must belong to its processor package or matching report module')
        handler = getattr(importlib.import_module(module_name), function_name)
        if not callable(handler):
            raise ValueError('handler is not callable')
        return handler
    except (ImportError, AttributeError, ValueError) as error:
        raise ReportError('could not load {0} {1} handler: {2}'.format(name, action, error)) from error


def rule_help():
    return '\n'.join('  {0:23} {1:9} {2}'.format(name, rule_type, description)
                     for name, rule_type, description in rule_catalog())
