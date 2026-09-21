# -*- coding: utf-8 -*-
"""Automatic checkup overview with per-field CSV findings."""
import os
import time
from urllib.parse import unquote, urlsplit
from dq.progress import Progress
from dq.csv_files import FieldCsvFiles
from dq.files import write_text, field_rule_output_paths, display_path
from dq.limits import scan_scope
from dq.field_selection import select_fields, DEFAULT_EXCLUDED_FIELDS
from dq.search import list_fields, collection_document_count, field_document_count, engine_name
from dq.errors import ReportError
from dq.reports._checkup.processor import plan, scan, ordered_checks, expanded_checks
from dq.reports.markdown import _table, _code, _results_first
from dq.reports.links import source_links


# Manually maintained, engine-specific reference values used only for the
# quick-checkup estimate. Do not apply one engine's measurements to another.
FULL_CHECKUP_BENCHMARKS = {
    'Solr': {
        'machine': 'MacBook Pro M4',
        'versions': 'Solr 9.10.1 and 10.0.0',
        'records_per_second_low': 15300.0,
        'records_per_second_high': 15800.0,
    },
    'Elasticsearch/OpenSearch': {
        'machine': 'MacBook Pro M4',
        'versions': 'Elasticsearch 9.5.3 and OpenSearch 3.8.0',
        'records_per_second_low': 16700.0,
        'records_per_second_high': 16800.0,
    },
}


def _target_name(target):
    """Return the collection/index name from a resolved target URL."""
    parts = [part for part in urlsplit(target).path.split('/') if part]
    return unquote(parts[-1]) if parts else target


def _runtime(seconds):
    if seconds < 0.01:
        return '< 0.01 seconds'
    if seconds < 60:
        return '{0:,.2f} seconds'.format(seconds)
    return '{0:.1f} minutes ({1:,.2f} seconds)'.format(seconds / 60.0, seconds)


def write_report(target, output_path, *, include=(), exclude=(), connection=None,
                 option_details=(), configuration_path=None, configuration_explicit=False, mode='full', report_name=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    report_name = report_name or ('quick_checkup' if mode == 'lite' else 'full_checkup')
    progress = Progress(report_name, enabled=mode == 'full')
    progress.update('loading search-engine schema and field inventory', force=True)
    selected = [f for f in select_fields(list_fields(target, include_counts=False, connection=connection),
                include=include, exclude=exclude) if f.get('stored') is True]
    if not selected:
        raise ReportError('checkup: no stored fields selected')
    plans = dict((f['name'], plan(f)) for f in selected)
    progress.update('counting collection documents', force=True)
    total = collection_document_count(target, connection=connection)
    missing = {}
    if mode == 'lite':
        presence_fields = [field for field in selected
                           if 'missing_fields_base' in expanded_checks(plans[field['name']])]
        for field in presence_fields:
            name = field['name']
            populated = field_document_count(target, name, connection=connection)
            missing[name] = max(0, total - populated)
        _write_lite(target, output_path, selected, plans, total, missing,
                    option_details, configuration_path, configuration_explicit, include, exclude,
                    report_name, row_limit, connection)
        progress.update('complete (no stored-value scan): ' + display_path(output_path), force=True)
        return [output_path]
    scan_total = total if row_limit == -1 else min(total, row_limit)
    scan_fields = [field for field in selected if expanded_checks(plans[field['name']])]
    field_rules = [(field, next(check for check in ordered_checks(plans[field['name']])
                                if check != 'missing_fields_base')
                          if any(check != 'missing_fields_base'
                                 for check in ordered_checks(plans[field['name']]))
                          else 'missing_fields_base')
                   for field in scan_fields]
    csv_paths = (field_rule_output_paths(os.path.dirname(output_path), field_rules, 'csv')
                 if scan_fields else {})
    csv_files = FieldCsvFiles(csv_paths, ['id', 'reason', 'value'])
    results = scan(target, selected, plans, connection, progress=progress, total=scan_total,
                   row_limit=row_limit, scan_progress=scan_progress, skip_null_values=skip_null_values,
                   on_finding=csv_files.add)
    if csv_paths:
        progress.update('writing CSV files', force=True)
    csv_files.flush()
    summary = []
    for field in selected:
        name = field['name']
        result = results[name]
        count = sum(result['counts'].values())
        summary.append((_code(name), '{0:,}'.format(count),
                        display_path(csv_paths[name]) if name in csv_paths else 'none'))
    elapsed = max(0.0, time.monotonic() - progress.started)
    lines = ['# Automatic Checkup — Full', '', 'Report: ' + _code(report_name), '', '- [Summary](#summary)', '- [Options Used](#options-used)',
             '- [Fields](#fields)', '', '## Summary', '',
             '- Collection: ' + _code(_target_name(target)),
             '- Documents: {0:,}'.format(total),
             '- Selected stored fields: ' + '{0:,}'.format(len(selected)),
             '- Full report runtime: ' + _runtime(elapsed),
             '- Include patterns: ' + _code(', '.join(include) or '*'),
             '- Exclude patterns: ' + _code(', '.join(exclude if include or exclude else DEFAULT_EXCLUDED_FIELDS) or 'none'),
             '- Fields with missing documents: ' + '{0:,}'.format(sum(
                 1 for result in results.values() if result['counts'].get('missing_fields_base', 0))),
             '- Value-check finding rows: ' + '{0:,}'.format(sum(sum(r['counts'].values()) for r in results.values())), '']
    lines += source_links(target)
    lines += [scan_scope(row_limit), '']
    lines += ['## Options Used', '']
    if configuration_path:
        lines += ['Configuration: ' + _code(configuration_path) + (' (specified by --config)' if configuration_explicit else ' (default configuration)'), '']
    lines += _table(('Option', 'Value', 'Source'), [(str(a), str(b), str(c)) for a,b,c in option_details])
    lines += ['', '## Fields', '',
              'Fields checked in collection/index ' + _code(_target_name(target)) + '; ' +
              '{0:,} documents scanned:'.format(results.documents_checked), '']
    lines += _table(('Field', 'Bad Values Reported', 'CSV File'), summary)
    # Publish overview last; failed scans never publish a new successful overview.
    progress.update('writing checkup overview', force=True)
    write_text(output_path, '\n'.join(_results_first(lines)) + '\n')
    progress.update('complete: ' + display_path(output_path), force=True)
    return [output_path] + list(csv_paths.values())


def _full_workload(selected, plans, total, row_limit=-1, engine='Solr'):
    fields = [field for field in selected
              if expanded_checks(plans[field['name']])]
    if not fields:
        return ['Performance: no stored-value rules are enabled for this field selection.', '']
    if row_limit == 0 or total == 0:
        return [('Performance: the document scan is disabled by `--rows 0`.' if row_limit == 0 else
                 'Performance: the collection is empty, so there are no documents to scan.'), '']
    documents = total if row_limit == -1 else min(total, row_limit)
    benchmark = FULL_CHECKUP_BENCHMARKS.get(engine)
    scope = ('all records and all fields' if row_limit == -1 else
             'up to {0:,} records and all selected fields'.format(documents))
    if benchmark:
        fastest_seconds = documents / benchmark['records_per_second_high']
        slowest_seconds = documents / benchmark['records_per_second_low']
        if slowest_seconds < 0.1:
            duration = '{0:.3f}-{1:.3f} seconds'.format(fastest_seconds, slowest_seconds)
        elif slowest_seconds < 1:
            duration = '{0:.2f}-{1:.2f} seconds'.format(fastest_seconds, slowest_seconds)
        elif slowest_seconds < 60:
            duration = '{0:.1f}-{1:.1f} seconds'.format(fastest_seconds, slowest_seconds)
        else:
            fastest_minutes = '{0:.1f}'.format(fastest_seconds / 60.0)
            slowest_minutes = '{0:.1f}'.format(slowest_seconds / 60.0)
            minute_text = (fastest_minutes + ' minutes' if fastest_minutes == slowest_minutes
                           else fastest_minutes + '-' + slowest_minutes + ' minutes')
            duration = '{0:.0f}-{1:.0f} seconds (about {2})'.format(
                fastest_seconds, slowest_seconds, minute_text)
        estimate = ('Estimated time: approximately {0} to scan {1}, based on reference '
                    '{2} timing on {3}.'.format(duration, scope, engine, benchmark['machine']))
    else:
        estimate = ('Estimated time: unavailable for {0}. The run will scan {1}.'
                    .format(engine, scope))
    return [estimate, '']


def _write_lite(target, output_path, selected, plans, total, missing, options,
                configuration, explicit, include, exclude, report_name, row_limit=-1,
                connection=None):
    rows = []
    for field in selected:
        name = field['name']
        suggestions = ordered_checks(set(plans[name]) - {'missing_fields_base'})
        suggestion_text = ', '.join(suggestions)
        automatic_matches = getattr(plans[name], 'automatic_matches', ())
        automatic_selected = getattr(plans[name], 'automatic_selected', None)
        if len(automatic_matches) > 1:
            alternatives = ['{0} ({1})'.format(rule, pattern)
                            for rule, pattern in automatic_matches
                            if rule != automatic_selected]
            suggestion_text = ('{0} (selected; also matched {1})'.format(
                automatic_selected, ', '.join(alternatives)))
        rows.append((_code(name), _code(str(field.get('type', 'unknown'))),
                     '{0:,}'.format(total - missing[name]) if name in missing else 'not checked',
                     '{0:,}'.format(missing[name]) if name in missing else 'not checked',
                     suggestion_text or ('missing_fields_base' if 'missing_fields_base' in plans[name] else 'Disabled')))
    lines = ['# Automatic Checkup — Quick', '', 'Report: ' + _code(report_name), '',
             '- [Run Additional Checks](#run-additional-checks)',
             '- [Summary](#summary)', '- [Options Used](#options-used)', '- [Fields](#fields)', '']
    lines += _followup_examples(target, selected, plans, total, configuration, explicit, row_limit)
    lines += ['## Summary', '',
             '- Check performed: count documents with and without a value for each selected field.',
             '- Collection: ' + _code(_target_name(target)),
             '- Documents: {0:,}'.format(total),
             '- Selected stored fields: ' + '{0:,}'.format(len(selected)),
             '- Include patterns: ' + _code(', '.join(include) or '*'),
             '- Exclude patterns: ' + _code(', '.join(exclude if include or exclude else DEFAULT_EXCLUDED_FIELDS) or 'none'),
             '']
    lines += source_links(target)
    current_total = collection_document_count(target, connection=connection)
    lines += ['## Options Used', '']
    if configuration:
        lines += ['Configuration: ' + _code(configuration) +
                  (' (specified by --config)' if explicit else ' (default configuration)'), '']
    lines += _table(('Option', 'Value', 'Source'), options)
    lines += ['', '## Fields', '',
              'Fields in collection/index ' + _code(_target_name(target)) +
              ', which contains {0:,} documents:'.format(current_total), '']
    lines += _table(('Field', 'Field type', 'Docs w/Value', 'Docs w/o Value', 'Matching Rule'), rows)
    write_text(output_path, '\n'.join(_results_first(lines)) + '\n')


def _followup_examples(target, selected, plans, total, configuration, configuration_explicit, row_limit):
    """Show focused, unexecuted commands for actual fields and planned rules."""
    import shlex
    lines = ['## Run Additional Checks', '',
             'Run a detailed report with:', '', '```sh',
             'bin/dq --report full_checkup', '```', '']
    lines += _full_workload(selected, plans, total, row_limit=row_limit,
                            engine=engine_name(target))
    lines += ['For large collections, during testing, consider limiting records with `--rows` or '
              '`--size`.', '', '```sh',
              'bin/dq --report full_checkup --rows 1000', '```', '']
    base = ['bin/dq']
    if configuration and configuration_explicit:
        base += ['--config', display_path(configuration)]
    examples = []
    seen = set()
    for field in selected:
        name = field['name']
        checks = [check for check in ordered_checks(plans[name])
                  if check != 'missing_fields_base']
        specialized = [check for check in checks
                       if 'field-name pattern' in plans[name].get(check, '')]
        rule = (specialized or checks or
                (['missing_fields_base'] if 'missing_fields_base' in plans[name] else [None]))[0]
        example_type = (str(field.get('type', 'unknown')), rule)
        if rule and example_type not in seen:
            seen.add(example_type)
            examples.append((name, rule))
    if not examples:
        return lines + ['No additional field checks are suggested for this selection.', '']
    commands = []
    for name, rule in examples:
        literal = ''.join({'*': '[*]', '?': '[?]', '[': '[[]'}.get(char, char) for char in name)
        command = base + ['--include_field', literal, '--rule', rule]
        commands.append(' '.join(shlex.quote(part) for part in command))
    return lines + ['### Analyze Specific Fields with Specific Rules', '',
                    '```sh'] + commands + ['```', '']
