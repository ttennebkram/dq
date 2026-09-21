"""Plan automatic checks and scan stored values once for the whole checkup."""
import re
from collections import Counter, OrderedDict
from dq import stored
from dq.findings import Finding
from dq.field_selection import is_text_field, is_date_field
from dq.rules.text.processor import value_reasons, blank_reason
from dq.rules.regex.definitions import definitions
from dq.rules.composites import COMPOSITES, expand
from dq.rules.chain import _failure

def _known_base_checks():
    """Return every base rule referenced by the loaded composites, in order."""
    result = []

    def visit(name):
        if name in COMPOSITES:
            for child in COMPOSITES[name]['rules']:
                visit(child)
        elif name not in result:
            result.append(name)

    for composite_name in COMPOSITES:
        visit(composite_name)
    return tuple(result)


BASE_CHECKS = _known_base_checks()
COMPOSITE_CHECKS = tuple(COMPOSITES)
CHECKS = BASE_CHECKS + COMPOSITE_CHECKS
_AUTOMATIC_RULES = None


class ScanResults(dict):
    """Per-field results with the completed source-document count."""
    documents_checked = 0


class RulePlan(OrderedDict):
    """Selected rules plus the automatic candidates considered for a field."""
    automatic_matches = ()
    automatic_selected = None


def expanded_checks(checks):
    base_checks = tuple(list(BASE_CHECKS) + [
        name for name in checks if name not in COMPOSITES and name not in BASE_CHECKS])
    execution_order = ([name for name in COMPOSITE_CHECKS if name in checks] +
                       [name for name in base_checks if name in checks])
    return expand(execution_order, base_checks)


def ordered_checks(checks):
    """One execution/display order: common prerequisites before special checks."""
    return ([name for name in CHECKS if name in checks] +
            sorted(name for name in checks if name not in CHECKS))


def _automatic_rules():
    """Return common metadata for every current base and composite rule."""
    global _AUTOMATIC_RULES
    if _AUTOMATIC_RULES is not None:
        return _AUTOMATIC_RULES
    from dq.registry import discover_rules
    result = discover_rules()
    result.update(definitions())
    result.update(COMPOSITES)
    _AUTOMATIC_RULES = result
    return _AUTOMATIC_RULES


def plan(field):
    name = field['name']
    text_field = is_text_field(field)
    # Split punctuation, underscores, and camelCase without matching substrings.
    words = set(re.findall('[a-z0-9]+', re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()))
    selected = {'missing_fields_base': 'all selected stored fields'}
    automatic_matches = ()
    automatic_selected = None
    if text_field and not field.get('uniqueKey'):
        matching = []
        fallbacks = []
        for check, definition in _automatic_rules().items():
            types = definition['automatic_field_types']
            if 'text' not in types:
                continue
            patterns = definition['automatic_field_name_patterns']
            if not patterns:
                fallbacks.append(check)
                continue
            matched = [pattern for pattern in patterns if set(pattern).issubset(words)]
            if matched:
                rendered = ' or '.join(' + '.join(pattern) for pattern in matched)
                matching.append((check, rendered,
                                 'inferred from field-name pattern: ' + rendered))
        if matching:
            matching.sort(key=lambda item: item[0])
            automatic_matches = tuple((check, rendered)
                                      for check, rendered, reason in matching)
            automatic_selected = matching[0][0]
            selected[automatic_selected] = matching[0][2]
        if not matching:
            for check in fallbacks:
                selected[check] = 'schema text/string field'
    if is_date_field(field):
        # Date analysis is deferred beyond the MVP, including explicit overrides.
        selected = ({'missing_fields_base': 'native date field: presence only in the MVP'}
                    if 'missing_fields_base' in selected else {})
        automatic_matches = ()
        automatic_selected = None
    if str(field.get('typeClass', '')).endswith('DenseVectorField'):
        # Vector arrays are only eligible for presence checks, even when a name
        # or explicit override would otherwise select a value rule.
        selected = ({'missing_fields_base': 'vector field: presence only; stored array not fetched'}
                    if 'missing_fields_base' in selected else {})
        automatic_matches = ()
        automatic_selected = None
    result = RulePlan((check, selected[check]) for check in ordered_checks(selected))
    result.automatic_matches = automatic_matches
    result.automatic_selected = automatic_selected
    return result


def scan(target, fields, plans, connection=None, progress=None, total=None, row_limit=-1, scan_progress=None, skip_null_values=False, on_finding=None):
    presets = definitions()
    results = ScanResults((f['name'], {'values': 0, 'text_values': 0, 'counts': Counter(),
                                      'examples': []}) for f in fields)
    selected = [f for f in fields if expanded_checks(plans[f['name']])]
    if not selected or total == 0:
        return results
    documents = [0]
    documents_seen = 0
    last_identifier = [None]
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
        scan_progress.show_fields = False
    for identifier, name, value in stored.values(target, selected, connection, progress=page_progress, include_null=True, row_limit=row_limit, scan_progress=scan_progress):
        if identifier != last_identifier[0]:
            documents_seen += 1
            last_identifier[0] = identifier
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
    completed_documents = max(documents[0], documents_seen)
    if scan_progress and scan_progress.measurements:
        completed_documents = scan_progress.measurements[-1]['records_checked']
    results.documents_checked = completed_documents
    if progress:
        progress.update('stored-value scan complete: {0:,} documents; {1:,} stored values'.format(
            completed_documents, values_seen), force=True)
    return results
