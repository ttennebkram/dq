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


def run_wizard(options):
    # Like --write_config, use only the destination file, not environment/parent defaults.
    from dq.settings import _resolve_field_filters, resolve_rows, resolve_progress_every, resolve_skip_null_values
    path = absolute_path(options.config or 'dq.ini')
    exists = os.path.isfile(path)
    config = load_config(path) if exists else DqConfig()
    rows = resolve_rows(options, config)
    print('Configuration Wizard')
    print('--------------------')
    print('This wizard will {0}: {1}'.format('update' if exists else 'create', path))
    if options.config:
        print('This file was selected with --config.')
    else:
        print('The default is dq.ini in your current directory.')
    print('To choose another file, press Ctrl-C and run:')
    print('  bin/dq --config_wizard --config FILE')
    print()
    print('Enter keeps the displayed default; - clears an optional value. Ctrl-C cancels.')
    print('Defaults come from command-line options, this destination file, then built-in suggestions.')
    url = options.main_url or config.main_url or 'http://localhost:8983/solr'
    collection = options.collection if options.collection is not None else (config.collection or 'dq-demo')
    print('For ES/OpenSearch, enter e.g. http://localhost:9200 (default port 9200).')
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
        username_default = (values['username'] or '').strip() or None
        username_label = ('username (Enter keeps saved value; - disables Basic authentication)'
                          if username_default else
                          'username (leave blank if not using Basic authentication)')
        values['username'] = _ask(username_label, username_default)
        if not values['username']:
            values['username'] = None
            values['password'] = None
        else:
            values['password'] = _ask('password (stored as plaintext in INI)', values['password'], secret=True)
        try:
            Connection(username=values['username'], password=values['password'])
            break
        except ConfigError as error:
            print('Invalid connection settings: {0}'.format(error))
    # Advanced certificate settings come only from CLI/INI; never prompt for them.
    if values['trust_certificate']:
        Connection(**values)
    # Keep advanced settings, accepting explicit CLI overrides without prompting.
    _resolve_field_filters(options, config)
    include = options.include_fields if options.field_filter_sources['include_fields'] != 'built-in default' else None
    exclude = options.exclude_fields if options.field_filter_sources['exclude_fields'] != 'built-in default' else None
    print('\nConfiguration to save: {0}'.format(path))
    print('Target: {0}'.format(target))
    print('rows: {0}{1}'.format(rows, ' (no limit)' if rows == -1 else ' (source documents per scan)'))
    for name in ('username', 'password', 'trust_certificate'):
        value = values[name]
        if name == 'trust_certificate' and not value:
            continue
        print('{0}: {1}'.format(name, '[redacted]' if name == 'password' and value is not None else value or '(none)'))
    for name, value in (('include_fields', include), ('exclude_fields', exclude)):
        if getattr(options, name) and options.field_filter_sources[name] == 'command line':
            print('{0} (command line): {1}'.format(name, value))
    while True:
        answer = input('Save configuration? [Y/n]: ').strip().lower()
        if answer in ('n', 'no'):
            print('Cancelled; no file written.')
            return 0
        if answer in ('', 'y', 'yes'):
            break
        print('Please enter yes or no.')
    write_config(path, url, collection, include_fields=include, exclude_fields=exclude,
                 preserve_optional=False,
                 reports_dir=getattr(options, 'reports_dir', None) if getattr(options, 'reports_dir', None) is not None else config.reports_dir, rows=rows, progress_every=resolve_progress_every(options, config), skip_null_values=resolve_skip_null_values(options, config), **values)
    print('Wrote configuration: {0}'.format(path))
    return 0
