"""Shared report dispatch and streaming CSV output, independent of report type."""
import os
import sys
from dq.config import ConfigError, load_config, collection_url
from dq.connection import make_connection
from dq.files import create_directory, field_output_paths, display_path, print_generated_files, absolute_path
from dq.csv_files import FieldCsvFiles
from dq.progress import ScanProgress
from dq.stats import FILENAME as STATS_FILENAME, save_scan_stats
from dq.processors import ReportError
from dq.processors.registry import load_handler
from dq.settings import _resolve_field_filters, _report_option_details, processor_directory, reports_directory, resolve_rows, resolve_progress_every, resolve_skip_null_values
from dq.solr import SolrError


def run_csv(options, parser):
    output = None
    try:
        rule_name = '_'.join(options.rule)
        config = load_config(options.config)
        _resolve_field_filters(options, config)
        row_limit = resolve_rows(options, config)
        connection = make_connection(options, config)
        target = collection_url(config, main_url=options.main_url,
                                collection=options.collection)
        directory = processor_directory(config)
        export = load_handler(options.rule, 'csv', directory) if directory else load_handler(options.rule, 'csv')
        if config.source:
            source = 'specified by --config' if options.config else 'default configuration'
            print('Configuration: {0} ({1})'.format(config.source, source), file=sys.stderr)
        scan_progress = ScanProgress(options.rule, resolve_progress_every(options, config))
        prepared = export(target, include=options.include_fields,
                               exclude=options.exclude_fields, connection=connection, row_limit=row_limit,
                               skip_null_values=resolve_skip_null_values(options, config),
                               scan_progress=scan_progress)
        if row_limit != -1:
            print('Maximum documents to check: {0:,}. Each field exports at most one CSV record per failing value. If multiple rules apply to one value, the first failure in the rule chain is reported.'.format(row_limit), file=sys.stderr)
        if not hasattr(prepared, 'fields'):
            raise ReportError('CSV processor must return field metadata using CsvExport')
        header, pages = prepared
        destination = reports_directory(options, config)
        paths = field_output_paths(destination, rule_name, prepared.fields, 'csv')
        if create_directory(destination):
            print('Created reports directory: {0}'.format(display_path(destination)), file=sys.stderr)
        output = FieldCsvFiles(paths, header)
        for batch in pages:
            output.write_page(batch)
        result_label = ('Passing records exported' if getattr(export, 'csv_results', 'failed') == 'succeeded'
                        else 'Offending records exported')
        if len(paths) > 1:
            print('\n{0} by field:'.format(result_label), file=sys.stderr)
            for field in paths:
                print('  {0}: {1:,}'.format(field, output.counts[field]), file=sys.stderr)
            print('Total {0} across all fields: {1:,} (Number of CSV records, not counting header row)'.format(
                result_label.lower(), output.written), file=sys.stderr)
        else:
            print('\n{0}: {1:,} (Number of CSV records, not counting header row)'.format(
                result_label, output.written), file=sys.stderr)
        generated = list(paths.values())
        stats_existed = os.path.isfile(os.path.join(destination, STATS_FILENAME))
        stats_path = save_scan_stats(destination, target, 'csv', rule_name, scan_progress,
                                     row_limit, resolve_skip_null_values(options, config))
        updated = []
        if stats_path:
            (updated if stats_existed else generated).append(stats_path)
        path_details = {}
        for field, path in paths.items():
            count = output.counts[field]
            path_details[absolute_path(path)] = '{0:,} data record{1}; header not counted'.format(
                count, '' if count == 1 else 's')
        print_generated_files(generated, updated_paths=updated, path_details=path_details)
    except (ConfigError, ReportError, SolrError, OSError) as error:
        parser.exit(
            2, '\ndq: error: {0}; export incomplete ({1:,} CSV records written)\n'.format(error, output.written if output else 0))
    except KeyboardInterrupt:
        parser.exit(
            130, '\ndq: interrupted; export incomplete ({0:,} CSV records written)\n'.format(output.written if output else 0))
    return 0

def run_reports(options, parser):
    try:
        config = load_config(options.config)
        _resolve_field_filters(options, config)
        row_limit = resolve_rows(options, config)
        connection = make_connection(options, config)
        target = collection_url(config, main_url=options.main_url, collection=options.collection)
        names = []
        for name in options.report:
            if name not in names:
                names.append(name)
        directory = processor_directory(config)
        handlers = [(name, load_handler(name, 'report', directory) if directory else load_handler(name, 'report')) for name in names]
        destination = reports_directory(options, config)
        if create_directory(destination):
            print('Created reports directory: {0}'.format(display_path(destination)))
        generated = []
        main_reports = []
        stats_existed_before_run = os.path.isfile(os.path.join(destination, STATS_FILENAME))
        for name, handler in handlers:
            output_path = os.path.join(destination, '{0}.md'.format(name))
            scan_progress = ScanProgress(name, resolve_progress_every(options, config), kind='report')
            written_paths = handler(target, output_path, include=options.include_fields,
                    exclude=options.exclude_fields, configuration_path=config.source,
                    configuration_explicit=bool(options.config),
                    option_details=_report_option_details(options, config, target, output_path),
                    connection=connection, row_limit=row_limit,
                    skip_null_values=resolve_skip_null_values(options, config),
                    scan_progress=scan_progress)
            written_paths = list(written_paths) if written_paths is not None else [output_path]
            generated.extend(written_paths)
            overview = [path for path in written_paths if absolute_path(path) == absolute_path(output_path)]
            # Reports without an overview use their field Markdown files as entry points.
            main_reports.extend(overview or [path for path in written_paths
                                            if os.path.splitext(str(path))[1].lower() == '.md'])
            stats_path = save_scan_stats(destination, target, 'report', name, scan_progress,
                                         row_limit, resolve_skip_null_values(options, config))
            if stats_path and stats_path not in generated:
                generated.append(stats_path)
        updated = []
        stats_path = os.path.join(destination, STATS_FILENAME)
        if stats_existed_before_run and stats_path in generated:
            generated.remove(stats_path)
            updated.append(stats_path)
        print_generated_files(generated, main_reports=main_reports, updated_paths=updated)
    except (ConfigError, ReportError, SolrError, OSError) as error:
        parser.exit(2, 'dq: error: {0}\n'.format(error))
    return 0
