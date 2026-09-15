"""Evaluate multiple CSV rules during one stored-value scan."""
from dq import stored
from dq.field_selection import is_text_field
from dq.findings import CsvExport, Finding
from dq.processors import ReportError
from dq.processors.code_points.processor import reasons as code_point_reasons
from dq.processors.standard_text.processor import blank_reason, value_reasons


def _regex_failure(definition, value):
    text = stored.text(value)
    for rule_name, kind, mode, expressions in definition['rules']:
        matched = any(expression.fullmatch(text) if mode == 'full' else expression.search(text)
                      for expression in expressions)
        passed = matched if kind == 'must_match' else not matched
        if not passed:
            return 'regex {0} {1} ({2})'.format(
                rule_name, 'matched' if matched else 'did not match', kind.replace('_', ' '))
    return None


def _failure(rule_name, regexes, field, value, skip_null_values):
    if rule_name == 'missing_fields':
        return 'missing_fields: missing or null' if value is None else None
    if rule_name == 'empty_strings':
        return 'empty_strings: empty string' if value == '' else None
    if rule_name == 'whitespace_only':
        return ('whitespace_only: whitespace-only string'
                if isinstance(value, str) and value != '' and value.isspace() else None)
    if rule_name == 'standard_text':
        reasons = value_reasons(value, skip_null_values=skip_null_values)
        return ('standard_text: ' + field + ': ' + reasons[0]) if reasons else None
    if rule_name == 'code_points':
        reasons = code_point_reasons(value) if isinstance(value, str) else []
        return ('code_points: ' + field + ': ' + reasons[0]) if reasons else None
    definition = regexes[rule_name]
    shared = value_reasons(value, skip_null_values=skip_null_values)
    if shared:
        return definition['name'] + ': ' + shared[0]
    if blank_reason(value):
        return None
    reason = _regex_failure(definition, value)
    return (definition['name'] + ': ' + reason) if reason else None


def handler(names, regexes):
    """Return a CSV handler whose values must pass every named rule in order."""
    label = ', '.join(names)

    def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1,
                    scan_progress=None, skip_null_values=False):
        selected = stored.fields(target, include, exclude, connection)
        if any(name in ('standard_text', 'code_points', 'empty_strings', 'whitespace_only') for name in names):
            selected = [field for field in selected if is_text_field(field)
                        and (include or not field.get('uniqueKey'))]
        if not selected:
            raise ReportError('{0}: no fields support every selected rule'.format(label))
        vectors = [field['name'] for field in selected
                   if str(field.get('typeClass', '')).endswith('DenseVectorField')]
        if vectors:
            raise ReportError('combined CSV rules do not support vector fields; exclude: {0}'.format(
                ', '.join(vectors)))

        def findings():
            values = stored.values(target, selected, connection, include_null=True,
                                   row_limit=row_limit, scan_progress=scan_progress)
            for identifier, field, value in values:
                for rule_name in names:
                    reason = _failure(rule_name, regexes, field, value, skip_null_values)
                    if reason:
                        yield Finding(field, (identifier, reason, '' if value is None else value))
                        break

        return CsvExport(selected, ['id', 'reason', 'value'], stored.pages(findings()))

    prepare_csv.csv_results = 'failed'
    return prepare_csv
