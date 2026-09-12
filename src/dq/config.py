"""Configuration discovery and target URL construction for DQ."""
import configparser
import os
from dq.files import absolute_path, write_text
from urllib.parse import quote, unquote, urlsplit


class ConfigError(ValueError):
    """The DQ configuration is missing or invalid."""


class DqConfig:
    """Resolved target settings and the file they came from."""

    def __init__(self, main_url=None, collection=None, source=None, username=None, password=None, trust_certificate=None,
                 include_fields=None, exclude_fields=None):
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
    values = dict(parser.defaults())
    if parser.has_section('dq'):
        values.update(parser.items('dq'))
    return DqConfig(main_url=values.get('main_url'),
                    collection=values.get('collection'), source=absolute_path(path),
                    username=values.get('username'), password=values.get('password'),
                    trust_certificate=values.get('trust_certificate'),
                    include_fields=_patterns(values.get('include_fields')),
                    exclude_fields=_patterns(values.get('exclude_fields')))


def load_config(explicit_path=None, start=None):
    """Load explicit, project, or user configuration and apply environment values."""
    if explicit_path:
        path = os.path.expanduser(str(explicit_path))
        if not os.path.isfile(path):
            raise ConfigError('configuration file does not exist: {0}'.format(path))
    else:
        path = _project_config(start or os.getcwd())
        if path is None:
            user_path = os.path.expanduser('~/.config/dq/config.ini')
            path = user_path if os.path.isfile(user_path) else None
    config = _read_config(path) if path else DqConfig()
    if explicit_path:
        return config
    return DqConfig(main_url=os.environ.get('DQ_MAIN_URL', config.main_url), collection=os.environ.get(
        'DQ_COLLECTION', config.collection), source=config.source, username=config.username, password=config.password,
        trust_certificate=config.trust_certificate, include_fields=config.include_fields,
        exclude_fields=config.exclude_fields)


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
                 include_fields=None, exclude_fields=None):
    """Atomically update target settings, commenting out changed old values."""
    normalized_main_url = main_url.rstrip('/')
    previous = _read_config(path) if os.path.isfile(path) else DqConfig()
    lines = ['[DEFAULT]']
    if previous.main_url and previous.main_url != normalized_main_url:
        lines.append('# Previous main_url = {0}'.format(previous.main_url))
    lines.append('main_url = {0}'.format(normalized_main_url))
    if previous.collection and previous.collection != collection:
        lines.append('# Previous collection = {0}'.format(previous.collection))
    if collection:
        lines.append('collection = {0}'.format(collection))
    for name, value in [('username', username), ('password', password),
                        ('trust_certificate', trust_certificate)]:
        if value is None:
            value = getattr(previous, name)
        if value is not None:
            if '\n' in value or '\r' in value:
                raise ConfigError('{0} must fit on one line'.format(name))
            lines.append('{0} = {1}'.format(name, value))
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
