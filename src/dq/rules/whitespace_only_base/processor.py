"""Export nonempty stored strings containing only whitespace."""
from dq import stored
from dq.field_selection import is_text_field
from dq.findings import Finding, CsvExport
from dq.errors import ReportError


def fields(target, include=(), exclude=(), connection=None):
    selected = [field for field in stored.fields(target, include, exclude, connection)
                if is_text_field(field) and (include or not field.get('uniqueKey'))]
    if not selected:
        raise ReportError('whitespace_only_base: no text/string fields selected')
    return selected


def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1,
                scan_progress=None, skip_null_values=False):
    selected = fields(target, include, exclude, connection)

    def findings():
        values = stored.values(target, selected, connection, row_limit=row_limit,
                               scan_progress=scan_progress)
        for identifier, field, value in values:
            if isinstance(value, str) and value != '' and value.isspace():
                yield Finding(field, (identifier, 'whitespace_only_base: whitespace-only string', value))
    return CsvExport(selected, ['id', 'reason', 'value'], stored.pages(findings()))
