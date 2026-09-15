"""Standard-output field listing."""
from dq.field_selection import select_fields
from dq.solr import list_fields
from dq.limits import PRESENCE_SCOPE
from dq.processors.registry import report_catalog, rule_catalog


def _yes_no(value):
    return 'yes' if value is True else 'no'


def _print_catalog(label, columns, rows):
    widths = [max([len(columns[index])] + [len(row[index]) for row in rows])
              for index in range(len(columns))]
    print('{0}: {1}'.format(label, len(rows)))
    print()
    print('  '.join(columns[index].ljust(widths[index]) for index in range(len(columns))))
    print('  '.join('-' * width for width in widths))
    for row in rows:
        print('  '.join(row[index].ljust(widths[index]) for index in range(len(columns))))


def print_reports():
    rows = [(name, status.title(), description)
            for name, status, description in report_catalog()]
    _print_catalog('Reports', ('REPORT', 'STATUS', 'DESCRIPTION'), rows)


def print_rules():
    rows = [(name, rule_type.title(), description)
            for name, rule_type, description in rule_catalog()]
    _print_catalog('Rules', ('RULE', 'TYPE', 'DESCRIPTION'), rows)


def print_fields(target, *, include=(), exclude=(), configuration_path=None,
                 configuration_explicit=False, connection=None, row_limit=-1):
    fields = select_fields(list_fields(target, connection=connection), include=include, exclude=exclude)
    columns = (('FIELD', 'name'), ('TYPE', 'type'), ('STORED', 'stored'), ('INDEXED', 'indexed'), ('DOC VALUES',
               'docValues'), ('MULTI VALUED', 'multiValued'), ('DOCUMENTS', 'documents'), ('SCHEMA FIELD', 'schemaField'))
    rows = [[str(field.get(key, '')) if key in {'name', 'type', 'documents', 'schemaField'} else _yes_no(
        field.get(key)) for _, key in columns] for field in fields]
    widths = [max([len(heading)] + [len(row[index]) for row in rows])
              for index, (heading, _) in enumerate(columns)]
    print('Solr collection: {0}'.format(target.rstrip('/')))
    if row_limit != -1:
        print(PRESENCE_SCOPE)
    if configuration_path is not None:
        source = 'specified by --config' if configuration_explicit else 'default configuration'
        print('Configuration: {0} ({1})'.format(configuration_path, source))
    print('Fields: {0}'.format(len(rows)))
    print()
    print('  '.join((heading.ljust(widths[index]) for index, (heading, _) in enumerate(columns))))
    print('  '.join(('-' * width for width in widths)))
    for row in rows:
        print('  '.join((value.ljust(widths[index]) for index, value in enumerate(row))))
