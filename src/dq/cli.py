"""Command-line entry point for DQ2."""
import argparse
import os
import sys
from dq.files import absolute_path
from dq.connection import connection_values, make_connection
from urllib.parse import unquote, urlsplit
from dq import __version__
from dq.config import ConfigError, DqConfig, collection_url, load_config, main_url_has_collection, write_config
from dq.field_selection import select_fields
from dq.reports import ReportError, write_empty_fields_report
from dq.solr import SolrError, list_fields, missing_id_pages
REPORT_NAMES = ('empty_fields', 'term_stats', 'code_points', 'date_checker')


def _yes_no(value):
    return 'yes' if value is True else 'no'


def _configured_value_source(*, command_line_value, environment_name, config, explicit_config):
    if command_line_value is not None:
        return 'command line'
    if explicit_config:
        return 'configuration file {0} specified by --config'.format(config.source)
    if environment_name in os.environ:
        return 'environment variable {0}'.format(environment_name)
    if config.source is not None:
        return 'default configuration file {0}'.format(config.source)
    return 'not set'


def _resolve_field_filters(options, config):
    sources = {}
    for name in ('include_fields', 'exclude_fields'):
        command_line = getattr(options, name)
        saved = getattr(config, name)
        if command_line:
            patterns = [pattern for pattern in command_line if pattern]
            sources[name] = 'command line'
        elif saved is not None:
            patterns = list(saved)
            origin = 'specified by --config' if options.config else 'default configuration'
            sources[name] = 'configuration file {0} ({1})'.format(config.source, origin)
        else:
            patterns = []
            sources[name] = 'built-in default'
        setattr(options, name, patterns)
    options.field_filter_sources = sources


def _report_option_details(options, config, target, output_path):
    main_url = options.main_url or config.main_url or ''
    main_url_source = _configured_value_source(
        command_line_value=options.main_url, environment_name='DQ_MAIN_URL', config=config, explicit_config=bool(options.config))
    if main_url_has_collection(main_url):
        path_parts = [unquote(part) for part in urlsplit(target).path.split('/') if part]
        collection = path_parts[-1]
        collection_source = 'included in main_url from {0}'.format(main_url_source)
    else:
        collection = options.collection or config.collection or ''
        collection_source = _configured_value_source(
            command_line_value=options.collection, environment_name='DQ_COLLECTION', config=config, explicit_config=bool(options.config))
    if config.source is None:
        configuration_value = 'none'
        configuration_source = 'no configuration file read'
    elif options.config:
        configuration_value = str(config.source)
        configuration_source = 'specified by --config'
    else:
        configuration_value = str(config.source)
        configuration_source = 'default configuration lookup'
    include_value = ', '.join(options.include_fields) or 'all fields'
    include_source = 'command line' if options.include_fields else 'built-in default'
    if options.exclude_fields:
        exclude_value = ', '.join(options.exclude_fields)
        exclude_source = 'command line'
    elif options.include_fields:
        exclude_value = 'none'
        exclude_source = 'built-in default with explicit field filters'
    else:
        exclude_value = '_*_'
        exclude_source = 'built-in default'
    details = [
        ('report', ', '.join(options.report), 'command line --report/--reports'),
        ('main_url', main_url, main_url_source),
        ('collection/index', collection, collection_source),
        ('configuration file', configuration_value, configuration_source),
        ('include_fields', include_value, include_source),
        ('exclude_fields', exclude_value, exclude_source),
        ('output file', str(output_path), 'built-in default'),
    ]
    for name, value in sorted(connection_values(options, config).items()):
        source = 'command line' if getattr(options, name) is not None else configuration_source
        if value is None:
            value, source = 'not set', 'built-in default'
        elif name == 'password':
            value = '[redacted]'
        details.append((name, value, source))
    sources = getattr(options, 'field_filter_sources', {})
    details = [(name, value, sources.get(name, source)) for name, value, source in details]
    return details



def print_fields(target, *, include=(), exclude=(), configuration_path=None,
                 configuration_explicit=False, connection=None):
    fields = select_fields(list_fields(target, connection=connection), include=include, exclude=exclude)
    columns = (('FIELD', 'name'), ('TYPE', 'type'), ('STORED', 'stored'), ('INDEXED', 'indexed'), ('DOC VALUES',
               'docValues'), ('MULTI VALUED', 'multiValued'), ('DOCUMENTS', 'documents'), ('SCHEMA FIELD', 'schemaField'))
    rows = [[str(field.get(key, '')) if key in {'name', 'type', 'documents', 'schemaField'} else _yes_no(
        field.get(key)) for _, key in columns] for field in fields]
    widths = [max([len(heading)] + [len(row[index]) for row in rows])
              for index, (heading, _) in enumerate(columns)]
    print('Solr collection: {0}'.format(target.rstrip('/')))
    if configuration_path is not None:
        source = 'specified by --config' if configuration_explicit else 'default configuration'
        print('Configuration: {0} ({1})'.format(configuration_path, source))
    print('Fields: {0}'.format(len(rows)))
    print()
    print('  '.join((heading.ljust(widths[index]) for index, (heading, _) in enumerate(columns))))
    print('  '.join(('-' * width for width in widths)))
    for row in rows:
        print('  '.join((value.ljust(widths[index]) for index, value in enumerate(row))))


class ExactArgumentParser(argparse.ArgumentParser):
    """Disable abbreviated options without requiring Python 3.5's allow_abbrev."""

    def _get_option_tuples(self, option_string):
        return []


def build_parser():
    parser = ExactArgumentParser(
        prog="dq",
        usage="""%(prog)s --report NAME [NAME ...] [options]
       %(prog)s --ids empty_fields [options]
       %(prog)s --list_fields [options]
       %(prog)s --write_config [options]
       %(prog)s --config_wizard [options]
       %(prog)s --help
       %(prog)s --version""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""\
DQ2 generates data-quality reports for Apache Solr, Elasticsearch,
and OpenSearch indexes.

Reports use Markdown so a run can produce multiple documents with links
between summary and detail pages. Stored fields are included by default;
include and exclude patterns will allow a run to focus on selected fields.

Choose exactly one action below. Shared options configure the target and
field selection; --ids requires exactly one selected stored field.""",
        epilog="""\
Saved target configuration:
  dq.ini in the current directory or a parent directory
  ~/.config/dq/config.ini as the user fallback
  INI include_fields/exclude_fields: one glob per line, indent continuation lines
  CLI filters replace the corresponding saved list; use an empty string to clear it

Reports:
  empty_fields   IMPLEMENTED - find fields that are not fully populated
  term_stats     PLANNED - analyze indexed terms and token lengths
  code_points    PLANNED - find tokens spanning unexpected Unicode classes
  date_checker   PLANNED - analyze stored date values and ranges

Planned utility and comparison commands:
  doc_count, diff_empty_fields, diff_ids, diff_schema, diff_config, dump_ids,
  delete_by_ids, solr_to_solr, solr_to_csv, hash_and_shard

Report example:
  dq --report empty_fields

Report selection:
  --report and --reports are equivalent; both accept one or more names

ID export (Solr, implemented):
  dq --ids empty_fields --include_field file_name_s > missing-ids.txt
  Select exactly one stored field. IDs go to stdout, diagnostics to stderr.
  Uses the schema unique key and cursor paging, 1,000 IDs per batch.

Field filtering examples (simple glob patterns, not regular expressions):
  --include_fields 'file_*' --include_fields 'content'
  --exclude_fields '*_vector' --exclude_fields '_*'

Project documentation:
  /Users/mbennett/Dropbox/dev/dq/README.md
""",
    )
    parser._optionals.title = "Options"
    actions = parser.add_argument_group("Actions (choose one)")
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {0}".format(__version__),
    )
    actions.add_argument(
        "--report",
        "--reports",
        metavar="NAME",
        action="append",
        nargs="+",
        choices=REPORT_NAMES,
        default=[],
        help="generate one or more named Markdown reports; repeatable",
    )
    actions.add_argument(
        "--ids", "-id", choices=("empty_fields",), metavar="NAME",
        help="stream missing-document IDs for exactly one selected stored field; no report file",
    )
    actions.add_argument(
        "--list_fields",
        "--list-fields",
        action="store_true",
        help="list Solr collection fields and their schema properties",
    )
    parser.add_argument(
        "--include_fields",
        "--include_field",
        "--include-fields",
        "--include-field",
        metavar="PATTERN",
        action="append",
        default=[],
        help="include simple glob patterns; repeatable; overrides INI include_fields; use '' to clear",
    )
    parser.add_argument(
        "--exclude_fields",
        "--exclude_field",
        "--exclude-fields",
        "--exclude-field",
        metavar="PATTERN",
        action="append",
        default=[],
        help="exclude simple glob patterns; repeatable; overrides INI exclude_fields; use '' to clear",
    )
    parser.add_argument(
        "--main_url",
        "--main-url",
        metavar="URL",
        help="server base URL, optionally including the collection or index",
    )
    parser.add_argument(
        "--collection",
        "--index",
        metavar="NAME",
        help="collection or index name (--index is a synonym)",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="read existing FILE; with --write_config or --config_wizard, create or update FILE",
    )
    actions.add_argument(
        "--write_config",
        "--write-config",
        action="store_true",
        help="write settings to ./dq.ini or the file named by --config",
    )
    actions.add_argument('--config_wizard', '--config-wizard', action='store_true',
                         help='interactively configure settings and save ./dq.ini or --config FILE')
    parser.add_argument('--username', metavar='NAME', help='HTTP Basic authentication username')
    parser.add_argument('--password', metavar='PASSWORD',
                        help='HTTP Basic password; prefer the INI file to shell history')
    parser.add_argument('--trust_certificate', '--trust-certificate', metavar='FILE',
                        help='PEM CA or self-signed certificate to trust; hostname checks remain enabled')
    return parser


def main(argv=None):
    parser = build_parser()
    arguments = list(argv) if argv is not None else sys.argv[1:]
    options = parser.parse_args(arguments)
    options.report = [name for group in options.report for name in group]
    action_count = sum((bool(options.config_wizard), bool(options.write_config), bool(
        options.list_fields), bool(options.report), bool(options.ids)))
    if action_count > 1:
        parser.error('choose only one action: --report, --ids, --list_fields, --write_config, or --config_wizard')
    if options.config_wizard:
        from dq.wizard import run_wizard
        try:
            return run_wizard(options)
        except (EOFError, KeyboardInterrupt):
            parser.exit(130, '\ndq: configuration wizard cancelled; no file written\n')
        except (ConfigError, OSError) as error:
            parser.exit(2, 'dq: error: {0}\n'.format(error))
    if options.ids:
        written = 0
        try:
            config = load_config(options.config)
            _resolve_field_filters(options, config)
            connection = make_connection(options, config)
            target = collection_url(config, main_url=options.main_url,
                                    collection=options.collection)
            fields = select_fields(list_fields(target, include_counts=False, connection=connection),
                                   include=options.include_fields, exclude=options.exclude_fields)
            if len(fields) != 1:
                names = ', '.join((str(field['name']) for field in fields)) or 'none'
                raise SolrError(
                    '--ids empty_fields requires exactly one field; matched {0}: {1}; narrow --include_field/--exclude_field'.format(len(fields), names))
            field = fields[0]
            if field.get('stored') is not True:
                raise SolrError(
                    '--ids empty_fields requires a stored field: {0}'.format(field['name']))
            print('Solr collection: {0}; missing field: {1}'.format(
                target, field['name']), file=sys.stderr)
            if config.source:
                source = 'specified by --config' if options.config else 'default configuration'
                print('Configuration: {0} ({1})'.format(config.source, source), file=sys.stderr)
            for ids in missing_id_pages(target, str(field['name']), connection=connection):
                for value in ids:
                    print(value)
                sys.stdout.flush()
                written += len(ids)
                if sys.stderr.isatty():
                    print('\rExported {0:,} IDs'.format(written),
                          end='', file=sys.stderr, flush=True)
            print('\nCompleted: {0:,} IDs exported.'.format(written), file=sys.stderr)
        except BrokenPipeError:
            with open(os.devnull, 'w') as sink:
                os.dup2(sink.fileno(), sys.stdout.fileno())
            return 0
        except (ConfigError, SolrError, OSError) as error:
            parser.exit(
                2, '\ndq: error: {0}; export incomplete ({1:,} IDs written)\n'.format(error, written))
        except KeyboardInterrupt:
            parser.exit(
                130, '\ndq: interrupted; export incomplete ({0:,} IDs written)\n'.format(written))
        return 0
    if options.write_config:
        try:
            output_path = absolute_path(
                options.config) if options.config else os.path.join(os.getcwd(), 'dq.ini')
            config = load_config(str(output_path)) if os.path.isfile(output_path) else DqConfig()
            resolved_main_url = options.main_url or config.main_url
            if not resolved_main_url:
                raise ConfigError(
                    'main_url is required; use --main_url, DQ_MAIN_URL, or an existing config')
            if options.main_url and main_url_has_collection(options.main_url):
                resolved_collection = options.collection
            else:
                resolved_collection = options.collection or config.collection
            collection_url(DqConfig(main_url=resolved_main_url, collection=resolved_collection))
            values = connection_values(options, config)
            if (values['username'] is None) != (values['password'] is None):
                raise ConfigError('username and password must be supplied together')
            _resolve_field_filters(options, config)
            write_config(output_path, resolved_main_url, resolved_collection,
                         include_fields=options.include_fields, exclude_fields=options.exclude_fields, **values)
            print('Wrote configuration: {0}'.format(output_path))
        except ConfigError as error:
            parser.exit(2, 'dq: error: {0}\n'.format(error))
        return 0
    if options.list_fields:
        try:
            config = load_config(options.config)
            _resolve_field_filters(options, config)
            connection = make_connection(options, config)
            target = collection_url(config, main_url=options.main_url,
                                    collection=options.collection)
            print_fields(target, include=options.include_fields, exclude=options.exclude_fields,
                         configuration_path=config.source, configuration_explicit=bool(options.config), connection=connection)
        except (ConfigError, SolrError) as error:
            parser.exit(2, 'dq: error: {0}\n'.format(error))
        return 0
    if options.report:
        try:
            config = load_config(options.config)
            _resolve_field_filters(options, config)
            connection = make_connection(options, config)
            target = collection_url(config, main_url=options.main_url,
                                    collection=options.collection)
            unimplemented = [name for name in options.report if name != 'empty_fields']
            if unimplemented:
                names = ', '.join(dict.fromkeys(unimplemented))
                raise ReportError('report not implemented yet: {0}'.format(names))
            output_path = os.path.join(os.getcwd(), 'report_empty_fields.md')
            write_empty_fields_report(target, output_path, include=options.include_fields, exclude=options.exclude_fields, configuration_path=config.source,
                                      configuration_explicit=bool(options.config), option_details=_report_option_details(options, config, target, output_path), connection=connection)
            print('Wrote report: {0}'.format(output_path))
        except (ConfigError, ReportError, SolrError) as error:
            parser.exit(2, 'dq: error: {0}\n'.format(error))
        return 0
    if not arguments:
        parser.print_help(sys.stderr)
    try:
        config = load_config(options.config)
        target = collection_url(config, main_url=options.main_url, collection=options.collection)
    except ConfigError as error:
        parser.exit(2, 'dq: error: {0}\n'.format(error))
    if config.source is None:
        configuration_detail = ''
    elif options.config:
        configuration_detail = ' using configuration file {0} specified by --config'.format(
            config.source)
    else:
        configuration_detail = ' using default configuration file {0}'.format(config.source)
    parser.exit(
        2, 'dq: error: target resolves to {0}{1}, but no action was selected; use --report NAME, --ids empty_fields, --list_fields, --write_config, or --config_wizard\n'.format(target, configuration_detail))
