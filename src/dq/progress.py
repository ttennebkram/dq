"""Throttled, flushed console progress for reports written to files."""
import datetime
import sys
import time


class Progress:
    def __init__(self, label, interval=5.0, enabled=True):
        self.enabled = enabled
        self.label = label
        self.interval = interval
        self.started = time.monotonic()
        self.last = None

    def update(self, message, force=False):
        if not self.enabled:
            return
        now = time.monotonic()
        if force or self.last is None or now - self.last >= self.interval:
            print('{0} [{1:.0f}s]: {2}'.format(self.label, now - self.started, message),
                  file=sys.stdout, flush=True)
            self.last = now


class ScanProgress:
    """Announce a scan and flush one dot for each configured document interval."""
    def __init__(self, label, every=1000, stream=None, kind='rule'):
        from dq.limits import progress_interval
        self.labels = list(label) if isinstance(label, (list, tuple)) else [label]
        self.label = ', '.join(self.labels)
        self.every = progress_interval(every)
        self.kind = kind
        self.field_rules = None
        self.show_fields = True
        self.stream = stream if stream is not None else sys.stdout
        self.active = False
        self.measurements = []

    def start(self, fields, unit='documents'):
        self.started = time.monotonic()
        self.unit = unit
        self.fields = list(fields)
        self.next_dot = self.every
        self.line_dots = 0
        self.active = True
        if not self.every:
            frequency = 'progress dots disabled'
        elif unit == 'documents':
            frequency = 'one dot per {0:,} records, shared across all listed fields'.format(self.every)
        else:
            frequency = 'one dot per {0:,} {1}'.format(self.every, unit)
        if self.show_fields:
            for field in fields:
                labels = ((self.field_rules or {}).get(field) or self.labels)
                label_kind = 'rules' if self.kind == 'rule' or self.field_rules is not None else self.kind
                print('Field: {0}; {1}: {2}'.format(field, label_kind, ', '.join(labels)),
                      file=self.stream, flush=True)
        print('Progress: {0}'.format(frequency), file=self.stream, flush=True)

    def update(self, count):
        if not self.every:
            return
        while count >= self.next_dot:
            print('.', end='', file=self.stream, flush=True)
            self.next_dot += self.every
            self.line_dots += 1
            if self.line_dots == 80:
                print(file=self.stream, flush=True)
                self.line_dots = 0

    def finish(self, count):
        if self.active:
            elapsed = max(0.0, time.monotonic() - self.started)
            self.measurements.append({
                'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'fields': self.fields, 'field_count': len(self.fields),
                'count_unit': self.unit, 'records_checked': count,
                'elapsed_seconds': elapsed,
                'records_per_second': count / elapsed if elapsed > 0 else None,
            })
            seconds = '{0:,.2f}'.format(elapsed) if elapsed >= 0.01 else '< 0.01'
            rate = ('{0:,.1f} records/second'.format(count / elapsed)
                    if elapsed > 0 else 'records/second unavailable')
            count_label = ('Documents checked' if self.unit == 'documents'
                           else self.unit.capitalize() + ' checked')
            field_scope = (' across {0:,} fields'.format(len(self.fields))
                           if self.unit == 'documents' and len(self.fields) > 1 else '')
            print('{0}{1}: {2:,}{3} in {4} seconds ({5})'.format(
                ' ' if self.line_dots else '', count_label, count, field_scope, seconds, rate),
                file=self.stream, flush=True)
            self.active = False
