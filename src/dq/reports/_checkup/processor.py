"""Plan automatic checks and scan stored values once for the whole checkup."""
import re
from collections import Counter, OrderedDict
from dq import stored
from dq.findings import Finding
from dq.field_selection import is_text_field, is_date_field
from dq.rules._text.processor import value_reasons, blank_reason
from dq.rules.regex.definitions import definitions
from dq.rules.composites import expand
from dq.rules.chain import _failure

BASE_CHECKS = ('missing_fields_base', 'empty_strings_base', 'whitespace_only_base',
               'surrounding_whitespace_base', 'code_points_base',
               'email_base', 'us_phone_base', 'ssn_base')
CHECKS = BASE_CHECKS + ('standard_text_composite', 'email_composite',
                        'us_phone_composite', 'ssn_composite')


def expanded_checks(checks):
    composite_checks = ('standard_text_composite', 'email_composite',
                        'us_phone_composite', 'ssn_composite')
    execution_order = ([name for name in composite_checks if name in checks] +
                       [name for name in BASE_CHECKS if name in checks])
    return expand(execution_order, BASE_CHECKS)


def ordered_checks(checks):
    """One execution/display order: common prerequisites before special checks."""
    return [name for name in CHECKS if name in checks]


def plan(field):
    name = field['name']
    text_field = is_text_field(field)
    # Split punctuation, underscores, and camelCase without matching substrings.
    words = set(re.findall('[a-z0-9]+', re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()))
    selected = {'missing_fields_base': 'all selected stored fields'}
    if text_field and not field.get('uniqueKey'):
        selected['standard_text_composite'] = 'schema text/string field'
    if text_field:
        for check, tokens in [('email_composite', {'email', 'mail'}),
                              ('us_phone_composite', {'phone', 'mobile', 'telephone', 'tel'}),
                              ('ssn_composite', {'ssn'})]:
            if words & tokens:
                selected[check] = 'inferred from field-name component: ' + ', '.join(sorted(words & tokens))
        if {'social', 'security'}.issubset(words):
            selected['ssn_composite'] = 'inferred from social/security field-name components'
    specialized = set(selected) & {'email_composite', 'us_phone_composite', 'ssn_composite'}
    if specialized:
        selected.pop('standard_text_composite', None)
    if not text_field:
        if not specialized:
            selected.pop('standard_text_composite', None)
        selected.pop('code_points_base', None)
    if is_date_field(field):
        # Date analysis is deferred beyond the MVP, including explicit overrides.
        selected = ({'missing_fields_base': 'native date field: presence only in the MVP'}
                    if 'missing_fields_base' in selected else {})
    if str(field.get('typeClass', '')).endswith('DenseVectorField'):
        # Vector arrays are only eligible for presence checks, even when a name
        # or explicit override would otherwise select a value rule.
        selected = ({'missing_fields_base': 'vector field: presence only; stored array not fetched'}
                    if 'missing_fields_base' in selected else {})
    return OrderedDict((name, selected[name]) for name in ordered_checks(selected))


def scan(target, fields, plans, connection=None, progress=None, total=None, row_limit=-1, scan_progress=None, skip_null_values=False, on_finding=None):
    presets = definitions()
    results = dict((f['name'], {'values': 0, 'text_values': 0, 'counts': Counter(),
                               'examples': []}) for f in fields)
    selected = [f for f in fields if set(expanded_checks(plans[f['name']])) - {'missing_fields_base'}]
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
            (field['name'], [name for name in expanded_checks(plans[field['name']])
                             if name != 'missing_fields_base'])
            for field in selected)
    for identifier, name, value in stored.values(target, selected, connection, progress=page_progress, include_null=True, row_limit=row_limit, scan_progress=scan_progress):
        values_seen += 1
        result = results[name]
        result['values'] += int(value is not None)
        result['text_values'] += int(isinstance(value, str))
        findings = []
        for check in expanded_checks(plans[name]):
            if progress and scan_progress is None:
                progress.update('field {0}; test {1}; {2:,} stored values; {3:,}{4} documents scanned'.format(
                    name, check, values_seen, documents[0],
                    ' / {0:,}'.format(total) if total is not None else ''))
            reason = _failure(check, presets, name, value, skip_null_values)
            if reason:
                leaf, detail = (reason.split(': ', 1) + [''])[:2]
                findings.append((leaf, detail))
                break
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
