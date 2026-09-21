"""Evaluate multiple CSV rules during one stored-value scan."""
from dq import stored
from dq.field_selection import is_text_field
from dq.findings import CsvExport, Finding
from dq.errors import ReportError
from dq.rules.procedural import failure_reason as procedural_failure_reason


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


def _failure(rule_name, regexes, field, value, skip_null_values,
             direct_missing_export=False):
    if value is None and skip_null_values and not (
            rule_name == 'missing_fields_base' and direct_missing_export):
        return None
    # Guard every base-rule implementation from dereferencing a null value.
    # Null remains a reportable failure unless the caller explicitly skips it.
    if value is None and rule_name != 'missing_fields_base':
        return rule_name + ': null value'
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
    if rule_name in regexes:
        definition = regexes[rule_name]
        reason = _regex_failure(definition, value)
        return (definition['name'] + ': ' + reason) if reason else None
    reason = procedural_failure_reason(rule_name, value)
    return (rule_name + ': ' + reason) if reason else None


def handler(names, regexes):
    """Return a CSV handler whose values must pass every named rule in order."""
    label = ', '.join(names)

    def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1,
                    scan_progress=None, skip_null_values=False):
        presence_only = names == ['missing_fields_base']
        selected = stored.fields(target, include, exclude, connection)
        if any(name != 'missing_fields_base' for name in names):
            selected = [field for field in selected if is_text_field(field)
                        and (include or not field.get('uniqueKey'))]
        if not selected:
            raise ReportError('{0}: no fields support every selected rule'.format(label))
        vectors = [field['name'] for field in selected
                   if str(field.get('typeClass', '')).endswith('DenseVectorField')]
        if vectors and not presence_only:
            raise ReportError('combined CSV rules do not support vector fields; exclude: {0}'.format(
                ', '.join(vectors)))

        def findings():
            values = stored.values(target, selected, connection, include_null=True,
                                   presence_only=presence_only, row_limit=row_limit,
                                   scan_progress=scan_progress)
            for identifier, field, value in values:
                if presence_only:
                    if value not in (True, False):
                        raise stored.SolrError('search engine did not return a boolean field-presence value')
                    value = object() if value else None
                for rule_name in names:
                    reason = _failure(rule_name, regexes, field, value, skip_null_values,
                                      direct_missing_export=presence_only)
                    if reason:
                        yield Finding(field, (identifier, reason, '' if value is None else value))
                        break

        return CsvExport(selected, ['id', 'reason', 'value'], stored.pages(findings()))

    prepare_csv.csv_results = 'failures'
    return prepare_csv
