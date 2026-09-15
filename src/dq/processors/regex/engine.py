"""Evaluate present stored values against each named regex rule."""
from dq import stored
from dq.findings import Finding, CsvExport


from dq.processors.standard_text.processor import blank_reason, value_reasons


def rule_reasons(definition, value):
    """Evaluate only regex rules; callers handle shared checks and blank values."""
    text = stored.text(value)
    for name, kind, mode, expressions in definition['rules']:
        match = any(expression.fullmatch(text) if mode == 'full' else expression.search(text)
                    for expression in expressions)
        passed = bool(match) if kind == 'must_match' else not bool(match)
        if passed == (definition['results'] == 'succeeded'):
            yield 'regex {0} {1} ({2})'.format(name, 'matched' if match else 'did not match',
                                             kind.replace('_', ' '))


def findings(definition, target, selected, connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    for identifier, field, value in stored.values(target, selected, connection, include_null=True, row_limit=row_limit, scan_progress=scan_progress):
        shared = value_reasons(value, skip_null_values=skip_null_values)
        if definition['results'] == 'failed':
            for reason in shared:
                yield Finding(field, (identifier, definition['name'] + ': ' + reason, '' if value is None else value))
        if blank_reason(value) or shared:
            continue
        for reason in rule_reasons(definition, value):
            yield Finding(field, (identifier, definition['name'] + ': ' + reason, stored.text(value)))
            break  # One CSV record per value, using the first selected rule result.


def handler(definition, action):
    headers = ['id', 'reason', 'value']
    def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
        selected = stored.fields(target, include, exclude, connection)
        return CsvExport(selected, headers, stored.pages(findings(definition, target, selected, connection, row_limit=row_limit, scan_progress=scan_progress, skip_null_values=skip_null_values)))
    if action == 'csv':
        # Let the CSV runner distinguish exported failures from passing matches.
        prepare_csv.csv_results = definition['results']
        return prepare_csv
    from dq.processors import ReportError
    raise ReportError(definition['name'] + ' is a rule; use --rule ' + definition['name'] + ' --action csv. For a report, use quick_checkup or full_checkup.')
