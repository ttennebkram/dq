"""Local timing history; one JSON object per completed scan, without field values."""
import datetime
import json
import os
import platform
import re
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

FILENAME = 'processing-stats.jsonl'
_MACHINE = None


def machine_description():
    """Return a useful non-identifying hardware label for timing comparisons."""
    global _MACHINE
    if _MACHINE is not None:
        return _MACHINE
    if sys.platform == 'darwin':
        try:
            output = subprocess.check_output(
                ['/usr/sbin/system_profiler', 'SPHardwareDataType', '-json'],
                stderr=subprocess.DEVNULL)
            hardware = json.loads(output.decode('utf-8'))['SPHardwareDataType'][0]
            family = re.search(r'\bM[0-9]+\b', hardware.get('chip_type', ''))
            if hardware.get('machine_name') and family:
                _MACHINE = hardware['machine_name'] + ' ' + family.group(0)
                return _MACHINE
        except (OSError, ValueError, KeyError, IndexError, subprocess.CalledProcessError):
            pass
    _MACHINE = ' '.join(value for value in (platform.system(), platform.machine()) if value) or 'unknown'
    return _MACHINE


def append_records(directory, records):
    path = os.path.join(directory, FILENAME)
    with open(path, 'a', encoding='utf-8', newline='\n') as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
    return path


def save_scan_stats(directory, target, action, name, progress, row_limit, skip_null_values):
    """Called only after an action succeeds; failed/aborted runs are not recorded."""
    if not progress.measurements:
        return None
    parts = urlsplit(target)
    clean_target = urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path, '', ''))
    records = []
    for measurement in progress.measurements:
        record = dict(measurement)
        record.update(source='dq', target=clean_target, action=action, name=name,
                      rows_limit=row_limit, skip_null_values=skip_null_values,
                      python_version=platform.python_version(), machine=machine_description())
        records.append(record)
    try:
        return append_records(directory, records)
    except OSError as error:
        print('dq: could not save processing stats: {0}'.format(error), file=sys.stderr)
        return None


def note_rate(directory, rate):
    """Record a user-provided observation without inventing missing run details."""
    return append_records(directory, [{
        'source': 'user-reported',
        'machine': machine_description(),
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'records_per_second': rate,
        'note': 'Run target, fields, rules, count, duration, and count unit were not supplied.'
    }])
