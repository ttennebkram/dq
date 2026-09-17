"""ISO date validation and a bounded histogram, using only the standard library."""
import datetime
import re
from dq import stored
from dq.findings import Finding, CsvExport
from dq.field_selection import is_date_field
from dq.rules._text.processor import blank_reason
from dq.errors import ReportError


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError('not an ISO date string')
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})?)?$', value)
    if not match:
        raise ValueError('expected ISO YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS[.fraction][Z|offset]')
    y, m, d, h, minute, sec, fraction, zone = match.groups()
    date = datetime.datetime(int(y), int(m), int(d), int(h or 0), int(minute or 0), int(sec or 0), int((fraction or '').ljust(6, '0')))
    if zone and zone != 'Z':
        hours, minutes = int(zone[1:3]), int(zone[4:6])
        if hours > 23 or minutes > 59:
            raise ValueError('invalid timezone offset')
        offset = datetime.timedelta(hours=hours, minutes=minutes)
        date = date - offset if zone[0] == '+' else date + offset
    return date


def select(target, include, exclude, connection):
    selected = stored.fields(target, include, exclude, connection)
    selected = [f for f in selected if is_date_field(f)]
    if not selected:
        raise ReportError('no native stored date fields selected; text date-format validation is outside the MVP')
    return selected


def findings(target, selected, connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    for identifier, field, value in stored.values(target, selected, connection, include_null=True, row_limit=row_limit, scan_progress=scan_progress):
        empty = blank_reason(value)
        if empty:
            yield Finding(field, (identifier, 'date_checker: empty_values: ' + empty, '' if value is None else value))
            continue
        try:
            date = parse_date(value)
            reason = 'future date' if date > now else None
        except (ValueError, OverflowError):
            reason = 'invalid ISO date'
        if reason:
            yield Finding(field, (identifier, 'date_checker: ' + field + ': ' + reason, stored.text(value)))


def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    selected = select(target, include, exclude, connection)
    return CsvExport(selected, ['id', 'reason', 'value'], stored.pages(findings(target, selected, connection, row_limit=row_limit, scan_progress=scan_progress)))
