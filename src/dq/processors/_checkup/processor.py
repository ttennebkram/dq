"""Plan automatic checks and scan stored values once for the whole checkup."""
import configparser
import re
from collections import Counter, OrderedDict
from fnmatch import fnmatchcase
from dq import stored
from dq.findings import Finding
from dq.field_selection import is_text_field, is_date_field
from dq.processors import ReportError
from dq.processors.code_points.processor import reasons
from dq.processors.standard_text.processor import value_reasons, blank_reason
from dq.processors.regex.definitions import definitions
from dq.processors.regex.engine import rule_reasons

CHECKS = ('missing_fields', 'empty_values', 'standard_text', 'code_points', 'email', 'us_phone', 'ssn')


def ordered_checks(checks):
    """One execution/display order: common prerequisites before special checks."""
    return [name for name in CHECKS if name in checks]


def overrides(path):
    if not path:
        return []
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with open(path, encoding='utf-8') as stream:
        parser.read_file(stream)
    # DEFAULT target settings are not checkup rules.
    parser.defaults().clear()
    if not parser.has_section('checkup'):
        return []
    result = []
    for pattern, value in parser.items('checkup'):
        checks = [part.strip() for part in value.split(',') if part.strip()]
        if checks == ['none']:
            checks = []
        if any(check not in CHECKS for check in checks):
            raise ReportError('unknown check in [checkup] for {0}; choose {1}, or none'.format(pattern, ', '.join(CHECKS)))
        result.append((pattern, list(OrderedDict.fromkeys(checks))))
    return result


def plan(field, rules):
    name = field['name']
    # Split punctuation, underscores, and camelCase without matching substrings.
    words = set(re.findall('[a-z0-9]+', re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()))
    selected = {'missing_fields': 'all selected stored fields'}
    if is_text_field(field) and not field.get('uniqueKey'):
        selected['standard_text'] = 'schema text/string field'
    for check, tokens in [('email', {'email', 'mail'}), ('us_phone', {'phone', 'mobile', 'telephone', 'tel'}),
                          ('ssn', {'ssn'})]:
        if words & tokens:
            selected[check] = 'inferred from field-name component: ' + ', '.join(sorted(words & tokens))
    if {'social', 'security'}.issubset(words):
        selected['ssn'] = 'inferred from social/security field-name components'
    matching = [(pattern, checks) for pattern, checks in rules if fnmatchcase(name, pattern)]
    if len(matching) > 1:
        raise ReportError('multiple [checkup] patterns match {0}; make overrides unambiguous'.format(name))
    if matching:
        pattern, checks = matching[0]
        selected = dict((check, 'explicit [checkup] override: ' + pattern) for check in checks)
    if set(selected) & {'email', 'us_phone', 'ssn'}:
        selected['standard_text'] = 'shared checks required by specialized text processor'
    if not is_text_field(field):
        if not set(selected) & {'email', 'us_phone', 'ssn'}:
            selected.pop('standard_text', None)
        selected.pop('code_points', None)
    if is_date_field(field):
        # Date analysis is deferred beyond the MVP, including explicit overrides.
        selected = ({'missing_fields': 'native date field: presence only in the MVP'}
                    if 'missing_fields' in selected else {})
    if str(field.get('typeClass', '')).endswith('DenseVectorField'):
        # Vector arrays are only eligible for presence checks, even when a name
        # or explicit override would otherwise select a value processor.
        selected = ({'missing_fields': 'vector field: presence only; stored array not fetched'}
                    if 'missing_fields' in selected else {})
    return OrderedDict((name, selected[name]) for name in ordered_checks(selected))


def scan(target, fields, plans, connection=None, progress=None, total=None, row_limit=-1, scan_progress=None, skip_null_values=False, on_finding=None):
    presets = definitions()
    results = dict((f['name'], {'values': 0, 'text_values': 0, 'counts': Counter(),
                               'examples': []}) for f in fields)
    selected = [f for f in fields if set(plans[f['name']]) - {'missing_fields'}]
    if not selected:
        return results
    documents = [0]
    values_seen = 0
    def page_progress(phase, count):
        documents[0] = count
        if progress and scan_progress is None:
            progress.update('{0}; {1:,}{2} documents scanned; {3:,} stored values checked'.format(
                'fetching next Solr page' if phase == 'fetching' else 'page complete',
                count, ' / {0:,}'.format(total) if total is not None else '', values_seen))
    if progress:
        progress.update('starting stored-value scan across {0} fields (one shared pass)'.format(len(selected)), force=True)
    if scan_progress:
        scan_progress.field_rules = dict(
            (field['name'], [name for name in ordered_checks(plans[field['name']])
                             if name != 'missing_fields'])
            for field in selected)
    for identifier, name, value in stored.values(target, selected, connection, progress=page_progress, include_null=True, row_limit=row_limit, scan_progress=scan_progress):
        values_seen += 1
        result = results[name]
        result['values'] += int(value is not None)
        result['text_values'] += int(isinstance(value, str))
        shared_enabled = 'standard_text' in plans[name] or bool(set(plans[name]) & set(presets))
        findings = [('standard_text', reason) for reason in value_reasons(value, skip_null_values=skip_null_values)] if shared_enabled else []
        empty = blank_reason(value)
        if not shared_enabled and 'empty_values' in plans[name] and empty:
            findings.append(('empty_values', empty))
        for check in ordered_checks(set(plans[name]) - {'missing_fields'}):
            if findings:
                break  # Stop this value at its first failure.
            if progress and scan_progress is None:
                progress.update('field {0}; test {1}; {2:,} stored values; {3:,}{4} documents scanned'.format(
                    name, check, values_seen, documents[0],
                    ' / {0:,}'.format(total) if total is not None else ''))
            if check in ('standard_text', 'empty_values') or ((shared_enabled or 'empty_values' in plans[name]) and empty):
                continue
            if check == 'code_points' and not shared_enabled and isinstance(value, str):
                findings += [(check, reason) for reason in reasons(value)[:1]]
            elif check in presets and not blank_reason(value):
                definition = dict(presets[check], results='failed')
                reason = next(rule_reasons(definition, value), None)
                if reason is not None:
                    findings.append((check, reason))
        for check, reason in findings:
            result['counts'][check] += 1
            if on_finding:
                on_finding(Finding(name, (identifier, check + ': ' + reason,
                                          '' if value is None else stored.text(value))))
            if len(result['examples']) < 100:
                result['examples'].append((identifier[:500], check + ': ' + reason, stored.text(value)[:500]))
    if progress:
        progress.update('stored-value scan complete: {0:,} documents; {1:,} stored values'.format(documents[0], values_seen), force=True)
    return results
