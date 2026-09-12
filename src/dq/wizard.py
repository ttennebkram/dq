"""Interactive configuration, without making server requests (Python 3.4+)."""
import getpass
import os
from dq.config import DqConfig, ConfigError, collection_url, load_config, main_url_has_collection, write_config
from dq.connection import Connection, connection_values
from dq.files import absolute_path


def _ask(label, default=None, secret=False):
    shown = '[saved password]' if secret and default is not None else default
    prompt = '{0}{1}: '.format(label, ' [{0}]'.format(shown) if shown else '')
    while True:
        value = getpass.getpass(prompt) if secret else input(prompt).strip()
        if '\n' in value or '\r' in value:
            print('Please enter a single line.')
            continue
        return default if value == '' else (None if value == '-' else value)


def _filters(label, defaults):
    print('{0}: {1}'.format(label, repr(defaults) if defaults else '(none)'))
    print('Enter keeps this list; - clears it; otherwise enter one glob per line, then an empty line.')
    first = input('First pattern: ').strip()
    if not first:
        return defaults
    if first == '-':
        return []
    patterns = [first]
    while True:
        value = input('Next pattern (Enter finishes): ').strip()
        if not value:
            return patterns
        patterns.append(value)


def run_wizard(options):
    # Like --write_config, use only the destination file, not environment/parent defaults.
    from dq.cli import _resolve_field_filters
    path = absolute_path(options.config or 'dq.ini')
    config = load_config(path) if os.path.isfile(path) else DqConfig()
    print('Configuration wizard: {0}'.format(path))
    print('Enter keeps the displayed default; - clears an optional value. Ctrl-C cancels.')
    print('Defaults come from command-line options and this destination file only.')
    url = options.main_url or config.main_url or 'http://localhost:8983/solr'
    collection = options.collection if options.collection is not None else config.collection
    while True:
        url = _ask('main_url', url)
        try:
            embedded = url and main_url_has_collection(url)
        except ValueError as error:
            print('Invalid target: {0}'.format(error))
            continue
        if embedded:
            print('Collection/index is included in main_url; the separate collection setting will be omitted.')
            collection = None
        else:
            collection = _ask('collection / index', collection)
        try:
            target = collection_url(DqConfig(main_url=url, collection=collection))
            break
        except (ConfigError, ValueError) as error:
            print('Invalid target: {0}'.format(error))
    values = connection_values(options, config)
    while True:
        values['username'] = _ask('username (optional Basic authentication)', values['username'])
        if values['username'] is None:
            values['password'] = None
        else:
            values['password'] = _ask('password (stored as plaintext in INI)', values['password'], secret=True)
        values['trust_certificate'] = _ask('trust_certificate (optional PEM path)', values['trust_certificate'])
        certificate = values['trust_certificate']
        if certificate:
            certificate = os.path.expanduser(certificate)
            if not os.path.isabs(certificate):
                certificate = os.path.join(os.path.dirname(path), certificate)
            values['trust_certificate'] = absolute_path(certificate)
        try:
            Connection(**values)
            break
        except ConfigError as error:
            print('Invalid connection settings: {0}'.format(error))
    _resolve_field_filters(options, config)
    include = _filters('include_fields (simple globs, not regex)', options.include_fields)
    exclude = _filters('exclude_fields (simple globs, not regex)', options.exclude_fields)
    print('\nConfiguration to save: {0}'.format(path))
    print('Target: {0}'.format(target))
    for name in ('username', 'password', 'trust_certificate'):
        value = values[name]
        print('{0}: {1}'.format(name, '[redacted]' if name == 'password' and value is not None else value or '(none)'))
    print('include_fields: {0}\nexclude_fields: {1}'.format(repr(include), repr(exclude)))
    if not include and not exclude:
        print('Default field exclusion applies: _*_')
    while True:
        answer = input('Save configuration? [Y/n]: ').strip().lower()
        if answer in ('n', 'no'):
            print('Cancelled; no file written.')
            return 0
        if answer in ('', 'y', 'yes'):
            break
        print('Please enter yes or no.')
    write_config(path, url, collection, include_fields=include, exclude_fields=exclude,
                 preserve_optional=False, **values)
    print('Wrote configuration: {0}'.format(path))
    return 0
