"""Configuration discovery and target URL construction for DQ."""
import configparser
import os
from dq.files import absolute_path, write_text
from dq.limits import row_limit, progress_interval, boolean_option
from urllib.parse import quote, unquote, urlsplit


class ConfigError(ValueError):
    """The DQ configuration is missing or invalid."""


class DqConfig:
    """Resolved target settings and the file they came from."""

    def __init__(self, main_url=None, collection=None, source=None, username=None, password=None, trust_certificate=None,
                 include_fields=None, exclude_fields=None, reports_dir=None, rows=None, progress_every=None, skip_null_values=None):
        self.skip_null_values = skip_null_values
        self.progress_every = progress_every
        self.rows = rows
        self.reports_dir = reports_dir
        self.main_url = main_url
        self.collection = collection
        self.source = source
        self.username = username
        self.password = password
        self.trust_certificate = trust_certificate
        self.include_fields = include_fields
        self.exclude_fields = exclude_fields


def _project_config(start):
    directory = absolute_path(start)
    while True:
        candidate = os.path.join(directory, 'dq.ini')
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _patterns(value):
    """INI patterns are one per line; spaces and commas within names are literal."""
    if value is None:
        return None
    return [line.strip() for line in value.splitlines() if line.strip()]


def _read_config(path):
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(str(path), encoding='utf-8') as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as error:
        raise ConfigError('could not read configuration {0}; check file access and INI syntax'.format(path)) from error
    defaults = dict(parser.defaults())
    # Resolve aliases within each layer so [dq] overrides [DEFAULT] even when
    # the two sections use different names for the document limit.
    parser.defaults().clear()
    specific = dict(parser.items('dq')) if parser.has_section('dq') else {}
    values = dict(defaults)
    values.update(specific)
    row_settings = specific if any(key in specific for key in ('rows', 'size')) else defaults
    limits = []
    try:
        limits = [row_limit(row_settings[key]) for key in ('rows', 'size') if key in row_settings]
        progress_every = progress_interval(values['progress_every']) if 'progress_every' in values else None
        skip_null_values = boolean_option(values['skip_null_values']) if 'skip_null_values' in values else None
    except ValueError as error:
        raise ConfigError('{0}: {1}'.format(path, error))
    if len(set(limits)) > 1:
        raise ConfigError('{0}: rows and size are synonyms; use one value per section'.format(path))
    rows = limits[0] if limits else None
    return DqConfig(main_url=values.get('main_url'), rows=rows, progress_every=progress_every, skip_null_values=skip_null_values,
                    collection=values.get('collection'), source=absolute_path(path),
                    username=values.get('username'), password=values.get('password'),
                    trust_certificate=values.get('trust_certificate'),
                    include_fields=_patterns(values.get('include_fields')),
                    exclude_fields=_patterns(values.get('exclude_fields')), reports_dir=values.get('reports_dir'))


def load_config(explicit_path=None, start=None):
    """Load an explicit or nearest project configuration and apply environment values."""
    if explicit_path:
        path = os.path.expanduser(str(explicit_path))
        if not os.path.isfile(path):
            raise ConfigError('configuration file does not exist: {0}'.format(path))
    else:
        path = _project_config(start or os.getcwd())
    config = _read_config(path) if path else DqConfig()
    if explicit_path:
        return config
    return DqConfig(main_url=os.environ.get('DQ_MAIN_URL', config.main_url), collection=os.environ.get(
        'DQ_COLLECTION', config.collection), source=config.source, username=config.username, password=config.password,
        trust_certificate=config.trust_certificate, include_fields=config.include_fields,
        exclude_fields=config.exclude_fields, reports_dir=config.reports_dir, rows=config.rows, progress_every=config.progress_every, skip_null_values=config.skip_null_values)


def collection_url(config, *, main_url=None, collection=None):
    """Resolve a complete collection URL from command-line and saved values."""
    resolved_main_url = main_url or config.main_url
    if not resolved_main_url:
        raise ConfigError('main_url is required; use --main_url, DQ_MAIN_URL, or a dq.ini file')
    parsed = urlsplit(resolved_main_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ConfigError('main_url must be an HTTP or HTTPS URL with a hostname')
    if parsed.username is not None or parsed.password is not None:
        raise ConfigError('use username/password settings instead of credentials in main_url')
    normalized_url = resolved_main_url.rstrip('/')
    path_parts = [unquote(part) for part in urlsplit(normalized_url).path.split('/') if part]
    has_collection_path = bool(path_parts) and path_parts != ['solr']
    if has_collection_path:
        collection_was_also_declared = collection is not None or (
            main_url is None and config.collection is not None)
        if collection_was_also_declared:
            raise ConfigError(
                'main_url already includes a collection or index; remove --collection/--index or the collection setting from dq.ini')
        return normalized_url
    resolved_collection = collection or config.collection
    if not resolved_collection:
        raise ConfigError(
            'collection is not present in main_url; use --collection, DQ_COLLECTION, or a dq.ini file')
    collection_path = quote(resolved_collection.strip('/'), safe='')
    return '{0}/{1}'.format(normalized_url, collection_path)


def main_url_has_collection(main_url):
    """Return whether a URL path appears to include a collection or index."""
    path_parts = [unquote(part) for part in urlsplit(main_url.rstrip('/')).path.split('/') if part]
    return bool(path_parts) and path_parts != ['solr']


def write_config(path, main_url, collection, username=None, password=None, trust_certificate=None,
                 include_fields=None, exclude_fields=None, preserve_optional=True, reports_dir=None, rows=None, progress_every=None, skip_null_values=None):
    """Atomically update target settings, commenting out changed old values."""
    normalized_main_url = main_url.rstrip('/')
    previous = _read_config(path) if os.path.isfile(path) else DqConfig()
    if rows is None and preserve_optional:
        rows = previous.rows
    if progress_every is None and preserve_optional:
        progress_every = previous.progress_every
    if skip_null_values is None and preserve_optional:
        skip_null_values = previous.skip_null_values
    try:
        skip_null_values = boolean_option(False if skip_null_values is None else skip_null_values)
        rows = row_limit(-1 if rows is None else rows)
        progress_every = progress_interval(1000 if progress_every is None else progress_every)
    except ValueError as error:
        raise ConfigError(str(error))
    lines = ['[DEFAULT]']
    if previous.main_url and previous.main_url != normalized_main_url:
        lines.append('# Previous main_url = {0}'.format(previous.main_url))
    lines.append('main_url = {0}'.format(normalized_main_url))
    if previous.collection and previous.collection != collection:
        lines.append('# Previous collection = {0}'.format(previous.collection))
    if collection:
        lines.append('collection = {0}'.format(collection))
    for name, value in [('username', username), ('password', password),
                        ('trust_certificate', trust_certificate), ('reports_dir', reports_dir)]:
        if value is None and preserve_optional:
            value = getattr(previous, name)
        if name == 'reports_dir' and previous.reports_dir is not None and previous.reports_dir != value:
            lines.append('# Previous reports_dir = {0}'.format(previous.reports_dir))
        if value is not None:
            if '\n' in value or '\r' in value:
                raise ConfigError('{0} must fit on one line'.format(name))
            lines.append('{0} = {1}'.format(name, value))
    if previous.rows is not None and previous.rows != rows:
        lines.append('# Previous rows = {0}'.format(previous.rows))
    lines.append('rows = {0}'.format(rows))
    if previous.progress_every is not None and previous.progress_every != progress_every:
        lines.append('# Previous progress_every = {0}'.format(previous.progress_every))
    lines.append('progress_every = {0}'.format(progress_every))
    if previous.skip_null_values is not None and previous.skip_null_values != skip_null_values:
        lines.append('# Previous skip_null_values = {0}'.format(str(previous.skip_null_values).lower()))
    lines.append('skip_null_values = {0}'.format(str(skip_null_values).lower()))
    for name, patterns in [('include_fields', include_fields), ('exclude_fields', exclude_fields)]:
        old_patterns = getattr(previous, name)
        if patterns is None:
            patterns = old_patterns
        if patterns is not None:
            if any('\n' in pattern or '\r' in pattern for pattern in patterns):
                raise ConfigError('{0} patterns must each fit on one line'.format(name))
            if old_patterns is not None and old_patterns != patterns:
                lines.append('# Previous {0}:'.format(name))
                lines.extend('#   ' + pattern for pattern in old_patterns)
            lines.append(name + ' =')
            lines.extend('    ' + pattern for pattern in patterns)
    contents = '\n'.join(lines) + '\n'
    try:
        write_text(path, contents)
    except OSError as error:
        raise ConfigError('could not write configuration {0}: {1}'.format(path, error)) from error
