# -*- coding: utf-8 -*-
"""Automatic checkup overview and linked per-field Markdown detail reports."""
import os
from dq.progress import Progress
from dq.csv_files import FieldCsvFiles
from dq.files import write_text, field_output_paths, field_option_details, display_path
from dq.limits import scan_scope, PRESENCE_SCOPE
from dq.field_selection import select_fields, DEFAULT_EXCLUDED_FIELDS
from dq.search import list_fields, collection_document_count, field_document_count, engine_name
from dq.errors import ReportError
from dq.reports._checkup.processor import plan, scan, ordered_checks, expanded_checks
from dq.reports.markdown import _table, _code, _results_first
from dq.reports.links import source_links


# Manually maintained reference values used only for the quick-checkup estimate.
FULL_CHECKUP_BENCHMARK_MACHINE = 'MacBook Pro M4'
FULL_CHECKUP_RECORDS_PER_SECOND_LOW = 18000.0
FULL_CHECKUP_RECORDS_PER_SECOND_HIGH = 25500.0


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
    for field in selected:
        progress.update('planned field {0}: {1}'.format(field['name'], ', '.join(ordered_checks(plans[field['name']])) or 'disabled'), force=True)
    progress.update('counting collection documents', force=True)
    total = collection_document_count(target, connection=connection)
    missing = {}
    for index, field in enumerate(selected, 1):
        name = field['name']
        if 'missing_fields_base' in expanded_checks(plans[name]):
            progress.update('field {0:,}/{1:,} {2}; test missing_fields_base (indexed presence)'.format(index, len(selected), name), force=True)
            # Indexed presence is distinct from the stored-value CSV scan.
            populated = field_document_count(target, name, connection=connection)
            missing[name] = max(0, total - populated)
    if mode == 'lite':
        _write_lite(target, output_path, selected, plans, total, missing,
                    option_details, configuration_path, configuration_explicit, include, exclude, report_name, row_limit)
        progress.update('complete (no stored-value scan): ' + display_path(output_path), force=True)
        return [output_path]
    paths = field_output_paths(os.path.dirname(output_path), report_name, selected, 'md')
    scan_total = total if row_limit == -1 else min(total, row_limit)
    value_fields = [field for field in selected
                    if set(expanded_checks(plans[field['name']])) - {'missing_fields_base'}]
    csv_paths = (field_output_paths(os.path.dirname(output_path), report_name, value_fields, 'csv')
                 if value_fields else {})
    csv_files = FieldCsvFiles(csv_paths, ['id', 'reason', 'value'])
    results = scan(target, selected, plans, connection, progress=progress, total=scan_total,
                   row_limit=row_limit, scan_progress=scan_progress, skip_null_values=skip_null_values,
                   on_finding=csv_files.add)
    csv_files.flush()
    summary = []
    selections = []
    for index, field in enumerate(selected, 1):
        name = field['name']
        result = results[name]
        progress.update('writing field report {0:,}/{1:,}: {2}'.format(index, len(selected), name), force=True)
        detail = paths[name]
        count = sum(result['counts'].values())
        summary.append((_code(name), '{0:,}'.format(total - missing[name]) if name in missing else 'not checked',
                        '{0:,}'.format(missing[name]) if name in missing else 'not checked',
                        '{0:,}'.format(count), '[Details](' + os.path.basename(detail) + ')',
                        '[CSV](' + os.path.basename(csv_paths[name]) + ')' if name in csv_paths else 'presence counts only'))
        for check, reason in [(check, plans[name][check]) for check in ordered_checks(plans[name])]:
            selections.append((_code(name), check, reason))
        lines = ['# Field: ' + _code(name), '', 'Report: ' + _code(report_name) + ' (field details)', '', '[Back to checkup](' + os.path.basename(output_path) + ')', '',
                 '## Checks Used', ''] + _table(('Check', 'Why'), [(check, plans[name][check]) for check in ordered_checks(plans[name])])
        lines += ['', '## Results', '', '- Missing documents: ' + ('{0:,}'.format(missing[name]) if name in missing else 'not checked'),
                  '- Non-null stored values scanned: ' + '{0:,}'.format(result['values']),
                  '- Stored text values scanned: ' + '{0:,}'.format(result['text_values']),
                  '- Finding rows: ' + '{0:,}'.format(count), '', scan_scope(row_limit), PRESENCE_SCOPE, '']
        lines += source_links(target, field)
        lines += _table(('Base rule', 'Findings'), [(check, '{0:,}'.format(count))
                                                    for check, count in result['counts'].items()])
        if name in csv_paths:
            lines += ['', '[All findings as CSV](' + os.path.basename(csv_paths[name]) + ')',
                      'CSV records: {0:,}. Columns: document ID, rule/reason, value. Full IDs and values; header excluded.'.format(csv_files.counts[name]), '']
        else:
            lines += ['', 'Presence counts only: stored values were not scanned for this field, so no CSV was created.', '']
        lines += ['', '## Example Findings', '', 'First 100 findings for this field; values truncated to 500 characters.', '']
        lines += _table(('id', 'reason', 'value'), [tuple(_code(v) for v in row) for row in result['examples']])
        lines += ['', '## Options Used', ''] + _table(('Option', 'Value', 'Source'),
            [(str(a), str(b), str(c)) for a, b, c in field_option_details(option_details, detail, name)])
        write_text(detail, '\n'.join(lines) + '\n')
    lines = ['# Automatic Checkup — Full', '', 'Report: ' + _code(report_name), '', '- [Summary](#summary)', '- [Options Used](#options-used)',
             '- [Check Selection](#check-selection)', '- [Fields](#fields)', '', '## Summary', '',
             '- Collection: ' + _code(target), '- Documents: {0:,}'.format(total),
             '- Selected stored fields: ' + '{0:,}'.format(len(selected)),
             '- Include patterns: ' + _code(', '.join(include) or '*'),
             '- Exclude patterns: ' + _code(', '.join(exclude if include or exclude else DEFAULT_EXCLUDED_FIELDS) or 'none'),
             '- Fields with missing documents: ' + '{0:,}'.format(sum(1 for value in missing.values() if value)),
             '- Value-check finding rows: ' + '{0:,}'.format(sum(sum(r['counts'].values()) for r in results.values())), '']
    lines += source_links(target)
    if configuration_path:
        lines += ['Configuration: ' + _code(configuration_path) + (' (specified by --config)' if configuration_explicit else ' (default configuration)'), '']
    lines += [scan_scope(row_limit), PRESENCE_SCOPE, '']
    lines += ['Checks inferred from names are suggestions; review Check Selection. A finding is not necessarily an error.',
              'Missing counts use search-engine field existence, not direct null inspection of stored records.',
              'Text checks expand arrays; skip_null_values optionally omits null findings. Shared empty-value, surrounding-whitespace, and Unicode checks run once per value, before regex rules. Native date fields receive presence checks only in the MVP.',
              'Unicode findings depend on the Python Unicode database. Regex checks validate syntax, not identity or deliverability.',
              'Linked field CSVs contain all findings from the same stored-value scan, with id,reason,value columns. Header-only CSVs indicate zero findings. Presence-only fields have counts but no CSV.',
              'If multiple rules apply to one value, the first failure in the rule chain is reported. Single-valued fields produce at most one finding per document; multivalued fields can produce one per failing value. This scan is not a snapshot.', '', '## Options Used', '']
    lines += _table(('Option', 'Value', 'Source'), [(str(a), str(b), str(c)) for a,b,c in option_details])
    lines += ['', '## Check Selection', ''] + _table(('Field', 'Check', 'Why'), selections)
    lines += ['', '## Fields', ''] + _table(('Field', 'Docs w/Value', 'Docs w/o Value', 'Value findings', 'Details', 'CSV'), summary)
    # Publish overview last; failed scans never publish a new successful overview.
    progress.update('writing checkup overview', force=True)
    write_text(output_path, '\n'.join(_results_first(lines)) + '\n')
    progress.update('complete: ' + display_path(output_path), force=True)
    return [output_path] + list(paths.values()) + list(csv_paths.values())


def _full_workload(selected, plans, total, row_limit=-1):
    fields = [field for field in selected
              if set(expanded_checks(plans[field['name']])) - {'missing_fields_base'}]
    checks = {}
    for field in fields:
        for check in set(expanded_checks(plans[field['name']])) - {'missing_fields_base'}:
            checks[check] = checks.get(check, 0) + 1
    lines = ['## Full Report Workload Estimate', '',
             'Scope: all fields selected in this report, using the same rows limit.', '',
             '- Collection documents: {0:,}'.format(total),
             '- Fields with presence checks: {0:,}'.format(sum('missing_fields_base' in expanded_checks(plans[f['name']]) for f in selected)), '']
    if not fields:
        lines += ['Only field-presence checks are enabled for this selection. Full checkup will query '
                  'document counts; it will not fetch stored values. No stored-value workload estimate applies.', '']
        return lines
    if row_limit == 0 or total == 0:
        lines += [('Stored-value scanning is disabled by rows = 0.' if row_limit == 0 else
                   'The collection is empty, so there are no documents to scan.'),
                  'Presence checks still run for their enabled fields.', '']
        return lines
    documents = total if row_limit == -1 else min(total, row_limit)
    batches = (documents + 999) // 1000
    fastest_seconds = documents / FULL_CHECKUP_RECORDS_PER_SECOND_HIGH
    slowest_seconds = documents / FULL_CHECKUP_RECORDS_PER_SECOND_LOW
    if slowest_seconds < 1:
        duration = '{0:.2f}-{1:.2f} seconds'.format(fastest_seconds, slowest_seconds)
    elif slowest_seconds < 60:
        duration = '{0:.1f}-{1:.1f} seconds'.format(fastest_seconds, slowest_seconds)
    else:
        duration = ('{0:.0f}-{1:.0f} seconds (approximately {2:.1f}-{3:.1f} minutes)'
                    .format(fastest_seconds, slowest_seconds,
                            fastest_seconds / 60.0, slowest_seconds / 60.0))
    lines += ['- Documents to scan: {0:,}'.format(documents),
              '- Stored fields to fetch per document: {0:,} (plus the unique key)'.format(len(fields)),
              '- Data pages at 1,000 documents per page: approximately {0:,}'.format(batches),
              '- Potential document/field pairs: {0:,}'.format(documents * len(fields)), '',
              '- Estimated stored-value scan time: ' + duration,
              '- Timing metric: {0:,.0f}-{1:,.0f} records/second on {2}'.format(
                  FULL_CHECKUP_RECORDS_PER_SECOND_LOW,
                  FULL_CHECKUP_RECORDS_PER_SECOND_HIGH,
                  FULL_CHECKUP_BENCHMARK_MACHINE), '',
              'The full report uses one shared scan, not a separate scan for each test. '
              'Cursor paging can add a final request to detect completion; reaching the rows limit ends the scan immediately. Schema and presence queries are additional.',
              'Missing fields reduce returned values; multivalued fields can add many values. '
              'Large text fields can dominate transfer and processing time. Date values and vector arrays are not fetched. '
              'Actual runtime can vary with field sizes, selected fields, server load, and network speed.', '']
    lines += _table(('Planned value check', 'Fields'), [(name, '{0:,}'.format(checks[name])) for name in ordered_checks(checks)])
    return lines


def _write_lite(target, output_path, selected, plans, total, missing, options,
                configuration, explicit, include, exclude, report_name, row_limit=-1):
    rows = []
    for field in selected:
        name = field['name']
        suggestions = ordered_checks(set(plans[name]) - {'missing_fields_base'})
        rows.append((_code(name), _code(str(field.get('type', 'unknown'))),
                     '{0:,}'.format(total - missing[name]) if name in missing else 'not checked',
                     '{0:,}'.format(missing[name]) if name in missing else 'not checked',
                     ', '.join(suggestions) or ('Presence check only' if 'missing_fields_base' in plans[name] else 'Disabled')))
    lines = ['# Automatic Checkup — Quick', '', 'Report: ' + _code(report_name), '', '- [Summary](#summary)',
             '- [Options Used](#options-used)', '- [Fields](#fields)',
             '- [Run Additional Checks](#run-additional-checks)',
             '- [Full Report Workload Estimate](#full-report-workload-estimate)', '', '## Summary', '',
             '- Scope: document counts for each selected field.',
             '- Collection: ' + _code(target), '- Documents: {0:,}'.format(total),
             '- Selected stored fields: ' + '{0:,}'.format(len(selected)),
             '- Include patterns: ' + _code(', '.join(include) or '*'),
             '- Exclude patterns: ' + _code(', '.join(exclude if include or exclude else DEFAULT_EXCLUDED_FIELDS) or 'none'),
             '',
             'Document counts come from {0} field-presence queries, counting each document once per field.'.format(engine_name(target)),
             'Native date and vector fields receive presence checks only in either mode.', PRESENCE_SCOPE, '']
    lines += source_links(target)
    if configuration:
        lines += ['Configuration: ' + _code(configuration) +
                  (' (specified by --config)' if explicit else ' (default configuration)'), '']
    lines += ['## Options Used', ''] + _table(('Option', 'Value', 'Source'), options)
    lines += ['', '## Fields', ''] + _table(('Field', 'Field type', 'Docs w/Value', 'Docs w/o Value', 'Additional checks in full report'), rows)
    lines += ['', 'Run `bin/dq --report full_checkup` to perform these additional checks.', '',
              'For large collections, we suggest choosing specific fields with `--include_fields` and limiting '
              'documents with `--rows` or its synonym `--size`.', '',
              'For example, replace FIELD with a field name from the table:', '',
              '```sh', 'bin/dq --report full_checkup --include_field FIELD --rows 1_000', '```', '',
              '`--size 1_000` is equivalent to `--rows 1_000`. The limit applies to the stored-value scan; '
              'presence counts still cover the entire collection.', '',
              'Suggested checks depend on schema types and field names: standard_text_composite for text/string fields; '
              'email_composite, us_phone_composite, and ssn_composite for matching name components. Native date fields get presence checks only. '
              'Full checkup performs the text and regex validation listed above.', '']
    lines += _followup_examples(target, selected, plans, missing, configuration, explicit, row_limit)
    lines += _full_workload(selected, plans, total, row_limit=row_limit) + ['']
    write_text(output_path, '\n'.join(_results_first(lines)) + '\n')


def _followup_examples(target, selected, plans, missing, configuration, configuration_explicit, row_limit):
    """Show focused, unexecuted commands for actual fields and planned rules."""
    import shlex
    lines = ['## Run Additional Checks', '',
             'These examples assume that `dq.ini` is in the current directory and sets `main_url` and `collection`. '
             'They were not executed. Run them from the same working directory as this checkup. '
             'They override saved field filters and limit source documents. '
             'Adjust --rows for your data; -1 removes the limit. Shell syntax below is for macOS/Linux.', '']
    base = ['bin/dq']
    if configuration and configuration_explicit:
        base += ['--config', display_path(configuration)]
    limit = row_limit if row_limit > 0 else 1000
    examples = []
    seen = set()
    for field in selected:
        name = field['name']
        checks = [check for check in ordered_checks(plans[name])
                  if check != 'missing_fields_base']
        specialized = [check for check in checks if check in
                       ('email_composite', 'us_phone_composite', 'ssn_composite')]
        rule = (specialized or checks or
                (['missing_fields_base'] if missing.get(name, 0) else [None]))[0]
        if rule and rule not in seen:
            seen.add(rule)
            examples.append((name, rule))
        if len(examples) == 3:
            break
    if not examples:
        return lines + ['No additional field checks are suggested for this selection.', '']
    for name, rule in examples:
        literal = ''.join({'*': '[*]', '?': '[?]', '[': '[[]'}.get(char, char) for char in name)
        common = base + ['--include_field', literal, '--exclude_fields', '', '--rows', str(limit)]
        lines += ['### ' + _code(name), '',
                  'Export findings from the ' + _code(rule) + ' rule:', '', '```sh',
                  ' '.join(shlex.quote(part) for part in common + ['--rule', rule, '--action', 'csv']), '```', '',
                  'Run the full checkup report for this field:', '', '```sh',
                  ' '.join(shlex.quote(part) for part in common + ['--report', 'full_checkup']), '```', '']
    return lines
