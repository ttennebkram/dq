"""Evaluate multiple CSV rules during one stored-value scan."""
from dq import stored
from dq.field_selection import is_text_field
from dq.findings import CsvExport, Finding
from dq.errors import ReportError
from dq.rules.code_points_base.processor import reasons as code_point_reasons
from dq.rules._text.processor import value_reasons


def _regex_failure(definition, value):
    text = stored.text(value)
    matched_name = None
    for rule_name, mode, expression in definition['rules']:
        matched = expression.fullmatch(text) if mode == 'full' else expression.search(text)
        if matched:
            matched_name = rule_name
            break
    if definition['report'] == 'no_match' and matched_name is None:
        return 'no configured regex matched'
    if definition['report'] == 'match' and matched_name is not None:
        return 'regex {0} matched'.format(matched_name)
    return None


def _failure(rule_name, regexes, field, value, skip_null_values):
    if value is None and skip_null_values:
        return None
    if rule_name == 'missing_fields_base':
        return 'missing_fields_base: missing or null' if value is None else None
    if rule_name == 'empty_strings_base':
        return 'empty_strings_base: empty string' if value == '' else None
    if rule_name == 'whitespace_only_base':
        return ('whitespace_only_base: whitespace-only string'
                if isinstance(value, str) and value != '' and value.isspace() else None)
    if rule_name == 'surrounding_whitespace_base':
        return ('surrounding_whitespace_base: leading or trailing whitespace'
                if isinstance(value, str) and value != value.strip() else None)
    if rule_name == 'code_points_base':
        reasons = code_point_reasons(value) if isinstance(value, str) else []
        return ('code_points_base: ' + field + ': ' + reasons[0]) if reasons else None
    definition = regexes[rule_name]
    reason = _regex_failure(definition, value)
    return (definition['name'] + ': ' + reason) if reason else None


def handler(names, regexes):
    """Return a CSV handler whose values must pass every named rule in order."""
    label = ', '.join(names)

    def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1,
                    scan_progress=None, skip_null_values=False):
        selected = stored.fields(target, include, exclude, connection)
        if any(name in ('missing_fields_base', 'code_points_base', 'empty_strings_base', 'whitespace_only_base',
                        'surrounding_whitespace_base') for name in names):
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

    prepare_csv.csv_results = 'failures'
    return prepare_csv
