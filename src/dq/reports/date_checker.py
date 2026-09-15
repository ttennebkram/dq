"""Date distribution graphs and Markdown report presentation."""
import datetime
import os
from collections import Counter
from dq import stored
from dq.files import write_text, field_output_paths, field_option_details
from dq.limits import scan_scope
from dq.reports.markdown import _table
from dq.reports.links import source_links
from dq.processors.date_checker.processor import select, parse_date


def histogram(counts, path):
    lo, hi = min(counts), max(counts)
    width = max(1, (hi - lo + 60) // 60)
    bins = Counter()
    for day, count in counts.items():
        bins[(day - lo) // width] += count
    n = (hi - lo) // width + 1
    peak = max(bins.values())
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="330" viewBox="0 0 900 330">',
           '<rect width="900" height="330" fill="white"/>',
           '<text x="60" y="24" font-family="sans-serif">Stored date values by time interval (UTC)</text>',
           '<path d="M60 45 V270 H870" fill="none" stroke="black"/>']
    for i in range(n):
        height = 210 * bins[i] / peak
        svg.append('<rect x="{0}" y="{1}" width="{2}" height="{3}" fill="#3978ad"><title>{4}: {5:,} values</title></rect>'.format(
            61 + 808 * i / n, 270 - height, max(.5, 808 / n - 1), height,
            datetime.date.fromordinal(lo + i * width).isoformat(), bins[i]))
    svg += ['<text x="60" y="292">{0}</text>'.format(datetime.date.fromordinal(lo).isoformat()),
            '<text x="780" y="292">{0}</text>'.format(datetime.date.fromordinal(hi).isoformat()),
            '<text x="60" y="318">Peak: {0:,} values; bin width: {1:,} day(s)</text>'.format(peak, width), '</svg>']
    write_text(path, '\n'.join(svg))
    return width


def write_report(target, output_path, *, include=(), exclude=(), connection=None,
                 option_details=(), configuration_path=None, configuration_explicit=False, row_limit=-1, scan_progress=None, skip_null_values=False):
    selected = select(target, include, exclude, connection)
    paths = field_output_paths(os.path.dirname(output_path), 'date_checker', selected, 'md')
    counts = dict((f['name'], Counter()) for f in selected)
    invalid = Counter()
    future = Counter()
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    for identifier, field, value in stored.values(target, selected, connection, row_limit=row_limit, scan_progress=scan_progress):
        try:
            date = parse_date(value)
            counts[field][date.date().toordinal()] += 1
            if date > now:
                future[field] += 1
        except (ValueError, OverflowError):
            invalid[field] += 1
    graph_paths = []
    metadata = dict((field['name'], field) for field in selected)
    for field, path in paths.items():
        c = counts[field]
        lines = ['# Date Checker', '', 'Report: `date_checker`', '', 'Field: ' + field, '',
                 '- [Summary](#summary)', '- [Options Used](#options-used)', '- [Distribution](#distribution)',
                 '', '## Summary', '', 'Source: stored values. Naive dates are interpreted as UTC. Nulls are skipped.',
                 'Graphs count values, not distinct documents; multivalued dates count individually.',
                 'Future dates are review indicators, not necessarily errors. Curve fitting is deferred.', '',
                 'Collection: ' + target, scan_scope(row_limit), '']
        lines += _table(('Field', 'Valid values', 'Invalid values', 'Future values', 'Earliest', 'Latest'),
            [(field, '{0:,}'.format(sum(c.values())), '{0:,}'.format(invalid[field]), '{0:,}'.format(future[field]),
              datetime.date.fromordinal(min(c)).isoformat() if c else '',
              datetime.date.fromordinal(max(c)).isoformat() if c else '')])
        lines += source_links(target, metadata[field])
        details = field_option_details(option_details, path, field)
        lines += ['', '## Options Used', ''] + _table(('Option', 'Value', 'Source'),
                                                    [(str(a), str(b), str(c)) for a, b, c in details])
        lines += ['', '## Distribution', '']
        if c:
            image = os.path.splitext(path)[0] + '_dates.svg'
            width = histogram(c, image)
            graph_paths.append(image)
            lines += ['![Date distribution](' + os.path.basename(image) + ')', '',
                      '[Open date graph](' + os.path.basename(image) + ')', '',
                      'Bin width: {0:,} day(s); up to 60 bins, including empty intervals.'.format(width), '']
        else:
            lines += ['No valid stored dates.', '']
        write_text(path, '\n'.join(lines) + '\n')
    return list(paths.values()) + graph_paths
