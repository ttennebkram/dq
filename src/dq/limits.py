"""Document scan limits shared by the CLI, configuration, and processors."""
import re


def boolean_option(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('true', 'yes', 'on', '1'):
            return True
        if normalized in ('false', 'no', 'off', '0'):
            return False
    raise ValueError('expected true or false')


def row_limit(value):
    message = 'rows must be -1 (no limit) or a non-negative integer'
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(message)
    if isinstance(value, str) and '_' in value:
        # int() gained underscore support in 3.6; normalize for Python 3.4.
        # Only accept single underscores between digits, not arbitrary removal.
        if not re.match(r'^[+-]?\d+(?:_\d+)*\Z', value.strip()):
            raise ValueError(message)
        value = value.replace('_', '')
    try:
        number = int(value)
    except ValueError:
        raise ValueError(message)
    if number < -1:
        raise ValueError(message)
    return number


def progress_interval(value):
    try:
        number = row_limit(value)
        if number >= 0:
            return number
    except ValueError:
        pass
    raise ValueError('progress_every must be a non-negative integer; 0 disables dots')


def scan_scope(limit):
    if limit == -1:
        return 'Stored-value scan: all documents (rows = -1; no limit).'
    if limit == 0:
        return 'Stored-value scan disabled (rows = 0); no documents examined.'
    return ('Stored-value scan: at most {0:,} documents in unique-key order '
            '(rows = {0}); this is not a random sample.').format(limit)


PRESENCE_SCOPE = ('Presence counts cover the entire collection; rows limits document '
                  'scans, not these counts.')
