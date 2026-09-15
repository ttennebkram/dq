"""Shared Markdown formatting with padded, vi-readable tables."""

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




def _results_first(lines):
    """Put navigation below the report identity, followed by field results."""
    lines = list(lines)
    start = lines.index('## Fields')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    results = ['## Results'] + lines[start + 1:end]
    remainder = lines[:start] + lines[end:]
    remainder = [line for line in remainder if line != '- [Fields](#fields)']
    navigation = next(i for i, line in enumerate(remainder) if line.startswith('- ['))
    navigation_end = navigation
    while navigation_end < len(remainder) and remainder[navigation_end].startswith('- ['):
        navigation_end += 1
    return (remainder[:navigation] + ['- [Results](#results)'] +
            remainder[navigation:navigation_end] + ['',] + results + [''] +
            remainder[navigation_end:])
