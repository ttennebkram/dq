"""Field metadata for shared scans, kept out of exported CSV columns."""


class Finding(tuple):
    """A normal row tuple with its original field name attached for routing."""
    def __new__(cls, field, values):
        row = tuple.__new__(cls, values)
        row.field = field
        return row


class CsvExport:
    """Selected fields and lazy CSV pages; supports header, pages unpacking."""
    def __init__(self, fields, header, pages):
        self.fields = [field['name'] for field in fields]
        self.header = header
        self.pages = pages

    def __iter__(self):
        yield self.header
        yield self.pages


def finding_field(row, names):
    """Resolve a row's field without inspecting reasons or guessing from globs."""
    from dq.processors import ReportError
    name = getattr(row, 'field', None)
    if name is None and len(names) == 1:
        return next(iter(names))
    if name not in names:
        raise ReportError('finding has no selected field; the processor must attach its original field name')
    return name
