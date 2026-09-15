"""Bounded CSV writing shared by rule exports and special reports."""
import csv
from collections import OrderedDict
from dq.findings import finding_field


class FieldCsvFiles:
    def __init__(self, paths, header):
        self.paths = paths
        self.counts = dict((name, 0) for name in paths)
        self.written = 0
        self.pending = []
        for path in paths.values():
            with open(path, 'w', encoding='utf-8', newline='') as stream:
                csv.writer(stream, lineterminator='\r\n').writerow(header)

    def write_page(self, rows):
        grouped = OrderedDict()
        for row in rows:
            grouped.setdefault(finding_field(row, self.paths), []).append(row)
        for name, group in grouped.items():
            with open(self.paths[name], 'a', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream, lineterminator='\r\n')
                for row in group:
                    writer.writerow(row)
                    self.written += 1
                    self.counts[name] += 1

    def add(self, finding):
        self.pending.append(finding)
        if len(self.pending) >= 1000:
            self.flush()

    def flush(self):
        self.write_page(self.pending)
        self.pending = []
