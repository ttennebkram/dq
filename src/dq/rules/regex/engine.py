"""Evaluate values against pure base regex rules."""
from dq import stored
from dq.findings import Finding, CsvExport


def rule_reasons(definition, value):
    """Evaluate only this definition's regex rules."""
    text = stored.text(value)
    matched_name = None
    for name, mode, expression in definition['rules']:
        match = expression.fullmatch(text) if mode == 'full' else expression.search(text)
        if match:
            matched_name = name
            break
    if definition['report'] == 'no_match' and matched_name is None:
        yield 'no configured regex matched'
    elif definition['report'] == 'match' and matched_name is not None:
        yield 'regex {0} matched'.format(matched_name)


def findings(definition, target, selected, connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    for identifier, field, value in stored.values(target, selected, connection, include_null=True, row_limit=row_limit, scan_progress=scan_progress):
        if value is None and skip_null_values:
            continue
        for reason in rule_reasons(definition, value):
            yield Finding(field, (identifier, definition['name'] + ': ' + reason,
                                  '' if value is None else stored.text(value)))
            break  # One CSV record per value, using the first selected rule result.


def handler(definition, action):
    headers = ['id', 'reason', 'value']
    def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
        selected = stored.fields(target, include, exclude, connection)
        return CsvExport(selected, headers, stored.pages(findings(definition, target, selected, connection, row_limit=row_limit, scan_progress=scan_progress, skip_null_values=skip_null_values)))
    if action == 'csv':
        # Let the CSV runner distinguish exported failures from passing matches.
        prepare_csv.csv_results = 'failures'
        return prepare_csv
    from dq.errors import ReportError
    raise ReportError(definition['name'] + ' is a rule; use --rule ' + definition['name'] + ' --action csv. For a report, use quick_checkup or full_checkup.')
