"""CLI action dispatch; implementations live in their own modules."""
import os
import sys
from dq.arguments import build_parser, resolve_selection
from dq.files import absolute_path
from dq.config import ConfigError, DqConfig, catalog_url, collection_url, load_config, main_url_has_collection, write_config
from dq.connection import connection_values, make_connection
from dq.settings import _resolve_field_filters, resolve_rows, resolve_progress_every, resolve_skip_null_values
from dq.listing import print_collections, print_fields, print_reports, print_rules
from dq.actions import run_reports, run_csv
from dq.solr import SolrError


def main(argv=None):
    parser = build_parser()
    arguments = list(argv) if argv is not None else sys.argv[1:]
    options = parser.parse_args(arguments)
    resolve_selection(options, parser)
    if options.list_reports:
        print_reports()
        return 0
    if options.list_rules:
        print_rules()
        return 0
    if options.config_wizard:
        from dq.wizard import run_wizard
        try:
            return run_wizard(options)
        except (EOFError, KeyboardInterrupt):
            parser.exit(130, '\ndq: configuration wizard cancelled; no file written\n')
        except (ConfigError, OSError) as error:
            parser.exit(2, 'dq: error: {0}\n'.format(error))
    if options.list_collections or options.list_indexes:
        try:
            config = load_config(options.config)
            connection = make_connection(options, config)
            target = catalog_url(config, main_url=options.main_url)
            noun = 'indexes' if options.list_indexes else 'collections'
            print_collections(target, noun=noun, configuration_path=config.source,
                              configuration_explicit=bool(options.config), connection=connection)
        except (ConfigError, SolrError) as error:
            parser.exit(2, 'dq: error: {0}\n'.format(error))
        return 0
    if options.action == 'csv' and options.rule:
        return run_csv(options, parser)
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
                         include_fields=options.include_fields, exclude_fields=options.exclude_fields,
                         reports_dir=options.reports_dir if options.reports_dir is not None else config.reports_dir,
                         rows=resolve_rows(options, config), progress_every=resolve_progress_every(options, config), skip_null_values=resolve_skip_null_values(options, config), **values)
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
                         configuration_path=config.source, configuration_explicit=bool(options.config), connection=connection, row_limit=resolve_rows(options, config))
        except (ConfigError, SolrError) as error:
            parser.exit(2, 'dq: error: {0}\n'.format(error))
        return 0
    if options.report:
        return run_reports(options, parser)
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
    if options.action == 'report':
        missing = 'no report was selected; use --report NAME with --action report'
    elif options.action == 'csv':
        missing = 'no rule was selected; use --rule NAME with --action csv'
    elif options.rule:
        missing = 'no action was selected; use --action csv with the selected rule'
    else:
        missing = ('no rule/action, report, or utility command was selected; use --rule NAME --action csv, --report NAME, '
                   '--list_fields, --list_collections/--list_indexes, --list_reports, --list_rules, --write_config, or --config_wizard')
    parser.exit(2, 'dq: error: target resolves to {0}{1}, but {2}\n'.format(target, configuration_detail, missing))
