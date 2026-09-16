"""Resolve field filters and describe the sources of effective options."""
import os
from urllib.parse import unquote, urlsplit
from dq.config import ConfigError, main_url_has_collection
from dq.limits import row_limit, progress_interval
from dq.connection import connection_values


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


def resolve_rows(options, config):
    supplied = getattr(options, 'rows', None)
    value = supplied if supplied is not None else config.rows
    try:
        return row_limit(-1 if value is None else value)
    except ValueError as error:
        raise ConfigError(str(error))


def resolve_progress_every(options, config):
    supplied = getattr(options, 'progress_every', None)
    value = supplied if supplied is not None else config.progress_every
    try:
        return progress_interval(1000 if value is None else value)
    except ValueError as error:
        raise ConfigError(str(error))


def resolve_skip_null_values(options, config):
    from dq.limits import boolean_option
    supplied = getattr(options, 'skip_null_values', None)
    value = supplied if supplied is not None else config.skip_null_values
    try:
        return boolean_option(False if value is None else value)
    except ValueError as error:
        raise ConfigError('skip_null_values: ' + str(error))


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
        ('rules', 'selected by the report', 'report implementation'),
        ('action', getattr(options, 'action', None) or 'report',
         getattr(options, 'action_source', 'command line --report/--reports shorthand')),
        ('main_url', main_url, main_url_source),
        ('collection/index', collection, collection_source),
        ('configuration file', configuration_value, configuration_source),
        ('include_fields', include_value, include_source),
        ('exclude_fields', exclude_value, exclude_source),
        ('reports_dir', reports_directory(options, config),
         'command line' if getattr(options, 'reports_dir', None) is not None else
         (configuration_source if config.reports_dir else 'built-in default')),
        ('rows', str(resolve_rows(options, config)),
         'command line' if getattr(options, 'rows', None) is not None else
         (('configuration file {0} ({1})'.format(
             config.source, 'specified by --config' if options.config else 'default configuration'))
          if config.rows is not None else 'built-in default (-1 means no limit)')),
        ('progress_every', str(resolve_progress_every(options, config)),
         'command line' if getattr(options, 'progress_every', None) is not None else
         (configuration_source if config.progress_every is not None else 'built-in default')),
        ('skip_null_values', str(resolve_skip_null_values(options, config)).lower(),
         'command line' if getattr(options, 'skip_null_values', None) is not None else
         (configuration_source if config.skip_null_values is not None else 'built-in default')),
        ('output file', str(output_path), 'rule name within reports_dir'),
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

def reports_directory(options, config):
    supplied = getattr(options, 'reports_dir', None)
    saved = getattr(config, 'reports_dir', None)
    value = os.path.expanduser(supplied if supplied is not None else (saved or 'reports'))
    if not value.strip():
        from dq.config import ConfigError
        raise ConfigError('reports_dir must not be empty')
    if supplied is None and saved and config.source and not os.path.isabs(value):
        value = os.path.join(os.path.dirname(config.source), value)
    return os.path.abspath(value)
