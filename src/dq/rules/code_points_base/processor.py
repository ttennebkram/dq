"""Unicode indicators are findings for review, not proof of corruption."""
import unicodedata
from dq import stored
from dq.findings import Finding, CsvExport
from dq.field_selection import is_text_field
from dq.errors import ReportError


def reasons(value):
    found = []
    buckets = set()
    for char in value:
        category = unicodedata.category(char)
        if char == '\ufffd' or category in ('Cs', 'Co', 'Cn', 'Cf') or (category == 'Cc' and char not in '\t\r\n'):
            bucket = {
                'Cs': 'surrogate', 'Co': 'private-use', 'Cn': 'unassigned',
                'Cf': 'format', 'Cc': 'control',
            }.get(category, 'replacement')
            if char == '\ufffd':
                bucket = 'replacement'
            buckets.add(bucket)
            found.append('U+{0:04X} {1} ({2})'.format(
                ord(char), unicodedata.name(char, 'UNNAMED'), category))
    if len(buckets) < 3:
        return []
    summary = '{0} suspicious code-point buckets: {1}'.format(
        len(buckets), ', '.join(sorted(buckets)))
    return [summary] + sorted(set(found))


def findings(target, selected, connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    for identifier, field, value in stored.values(target, selected, connection, row_limit=row_limit, scan_progress=scan_progress):
        if isinstance(value, str):
            for reason in reasons(value)[:1]:
                yield Finding(field, (identifier, 'code_points_base: ' + field + ': ' + reason, value))


def fields(target, include=(), exclude=(), connection=None):
    selected = [field for field in stored.fields(target, include, exclude, connection)
                if is_text_field(field) and (include or not field.get('uniqueKey'))]
    if not selected:
        raise ReportError('code_points_base: no text/string fields selected')
    return selected


def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    selected = fields(target, include, exclude, connection)
    return CsvExport(selected, ['id', 'reason', 'value'], stored.pages(findings(target, selected, connection, row_limit=row_limit, scan_progress=scan_progress)))
