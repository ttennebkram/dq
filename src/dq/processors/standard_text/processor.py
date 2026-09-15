"""Unicode indicators are findings for review, not proof of corruption."""
from dq.processors.code_points.processor import reasons
from dq import stored
from dq.findings import Finding, CsvExport
from dq.field_selection import is_text_field
from dq.processors import ReportError


def blank_reason(value):
    if value is None:
        return 'null'
    if isinstance(value, str):
        if value == '':
            return 'empty string'
        if value.isspace():
            return 'whitespace only'
    return None


def value_reasons(value, skip_null_values=False):
    """Return the first failed check per value, before specialized regex rules."""
    if value is None and skip_null_values:
        return []
    blank = blank_reason(value)
    if blank:
        return ['empty_values: ' + blank]
    if not isinstance(value, str):
        return []
    if value != value.strip():
        return ['surrounding_whitespace: leading or trailing whitespace']
    unicode_reasons = reasons(value)
    return ['code_points: ' + unicode_reasons[0]] if unicode_reasons else []


def findings(target, selected, connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    for identifier, field, value in stored.values(target, selected, connection, include_null=True, row_limit=row_limit, scan_progress=scan_progress):
        for reason in value_reasons(value, skip_null_values=skip_null_values):
            yield Finding(field, (identifier, 'standard_text: ' + field + ': ' + reason, '' if value is None else value))


def fields(target, include=(), exclude=(), connection=None):
    selected = [field for field in stored.fields(target, include, exclude, connection)
                if is_text_field(field) and (include or not field.get('uniqueKey'))]
    if not selected:
        raise ReportError('standard_text: no text/string fields selected')
    return selected


def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    selected = fields(target, include, exclude, connection)
    return CsvExport(selected, ['id', 'reason', 'value'], stored.pages(findings(target, selected, connection, row_limit=row_limit, scan_progress=scan_progress, skip_null_values=skip_null_values)))
