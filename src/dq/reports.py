"""Markdown report generation for DQ."""

from dq.files import write_text
from dq.field_selection import DEFAULT_EXCLUDED_FIELDS, select_fields
from dq.solr import collection_document_count, list_fields


class ReportError(RuntimeError):
    """A report could not be written."""


def _format_patterns(patterns):
    return ', '.join('`' + pattern.replace('`', '\\`') + '`' for pattern in patterns)


def _code(value):
    value = value.replace('\n', ' ')
    return '`` {0} ``'.format(value) if '`' in value else '`{0}`'.format(value)


def _table(headers, rows):
    """Pad pipe-table columns so the Markdown source is readable in vi."""
    cells = [
        [cell.replace('\r', ' ').replace('\n', ' ').replace('|', '\\|') for cell in row]
        for row in [headers] + list(rows)
    ]
    widths = [max([3] + [len(row[i]) for row in cells]) for i in range(len(headers))]

    def render(row):
        return '| ' + ' | '.join(cell.ljust(width) for cell, width in zip(row, widths)) + ' |'

    lines = [render(cells[0]), render(['-' * width for width in widths])]
    lines.extend(render(row) for row in cells[1:])
    return lines


def write_empty_fields_report(collection_url, output_path, *, include=(), exclude=(),
                              configuration_path=None, configuration_explicit=False,
                              option_details=()):
    """Write a Markdown report for stored fields missing from some documents."""
    total_documents = collection_document_count(collection_url)
    selected = select_fields(list_fields(collection_url), include=include, exclude=exclude)
    stored_fields = [field for field in selected if field.get('stored') is True]
    effective_exclude = exclude if include or exclude else DEFAULT_EXCLUDED_FIELDS
    incomplete = []
    for field in stored_fields:
        populated = int(field['documents'])
        missing = max(total_documents - populated, 0)
        if missing:
            incomplete.append((field, populated, missing))

    lines = [
        '# Empty Fields Report', '',
        '- [Summary](#summary)',
        '- [Options Used](#options-used)',
        '- [Fields](#fields)', '',
        '## Summary', '',
        '- Collection: `{0}`'.format(collection_url),
    ]
    if configuration_path is not None:
        source = 'specified by `--config`' if configuration_explicit else 'default configuration'
        lines.append('- Configuration: `{0}` ({1})'.format(configuration_path, source))
    lines.extend([
        '- Collection documents: {0:,}'.format(total_documents),
        '- Include field patterns: {0}'.format(_format_patterns(include)
                                               if include else 'all fields'),
        '- Exclude field patterns: {0}'.format(_format_patterns(effective_exclude)
                                               if effective_exclude else 'none'),
        '- Stored fields checked: {0:,}'.format(len(stored_fields)),
        '- Incomplete stored fields: {0:,}'.format(len(incomplete)),
        '', '## Options Used', '',
    ])
    lines.extend(_table(
        ('Option', 'Value', 'Source'),
        [(_code(name), _code(value), source) for name, value, source in option_details],
    ))
    lines.extend(['', '## Fields', ''])
    if incomplete:
        rows = []
        for field, populated, missing in incomplete:
            percentage = (populated / total_documents * 100) if total_documents else 0.0
            rows.append((
                _code(str(field.get('name', ''))), _code(str(field.get('type', ''))),
                '{0:,}'.format(populated), '{0:,}'.format(missing),
                '{0:.2f}%'.format(percentage),
            ))
        lines.extend(_table(
            ('Field', 'Type', 'Documents with a value', 'Missing documents', 'Populated'), rows,
        ))
    else:
        lines.append('All selected stored fields are populated in every document.')
    lines.extend([
        '',
        'A missing value means Solr did not detect the field in that document. '
        'An indexed empty string may still count as present.',
        '',
    ])
    try:
        write_text(output_path, '\n'.join(lines))
    except OSError as error:
        raise ReportError('could not write report {0}: {1}'.format(output_path, error)) from error
