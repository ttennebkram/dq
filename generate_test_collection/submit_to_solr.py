#!/usr/bin/env python3
"""Submit demo documents by ID; optionally recreate the local dq_demo collection."""
import argparse
import time
import errno
import stat
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from dq.config import load_config, catalog_url
from dq.connection import Connection
from dq.search import is_solr_target
from dq.solr import get_json

BATCH_SIZE = 5000


def required_dynamic_fields():
    """Read the suffix-based field definitions required by generated demo data."""
    path = os.path.join(os.path.dirname(__file__), 'schema_solr.json')
    with open(path, encoding='utf-8') as stream:
        definitions = json.load(stream).get('required_dynamic_fields')
    if not isinstance(definitions, list):
        raise ValueError('schema_solr.json must contain required_dynamic_fields')
    return definitions


def validate_dynamic_fields(collection_url, connection):
    """Require the _default configset mappings used by optional demo fields."""
    response = get_json(collection_url, 'schema/dynamicfields', connection=connection,
                        showDefaults='true', wt='json')
    fields = response.get('dynamicFields')
    if not isinstance(fields, list):
        raise ValueError('Solr Schema API did not return dynamic fields')
    available = dict((str(field.get('name')), str(field.get('type')))
                     for field in fields if isinstance(field, dict))
    missing = []
    for required in required_dynamic_fields():
        name = str(required.get('name'))
        expected = str(required.get('type'))
        actual = available.get(name)
        if actual != expected:
            missing.append('{0} -> {1} (found {2})'.format(
                name, expected, actual if actual is not None else 'nothing'))
    if missing:
        raise ValueError('dq_demo requires Solr dynamic fields: ' + '; '.join(missing))


def solr_base(config):
    """Resolve only the Solr server root; ignore any configured collection."""
    if not config.main_url or not is_solr_target(config.main_url):
        raise ValueError('dq.ini main_url must identify Solr when running submit_to_solr.py')
    return catalog_url(config)


def prepare_collection(base, connection, recreate=False):
    name = 'dq_demo'
    collections = get_json(base, 'admin/collections', connection=connection, action='LIST', wt='json')['collections']
    if name in collections and not recreate:
        return False
    configs = get_json(base, 'admin/configs', connection=connection, action='LIST', wt='json')['configSets']
    status = get_json(base, 'admin/collections', connection=connection, action='CLUSTERSTATUS', wt='json')
    cluster = status['cluster']['collections']
    dedicated = set([name, name + '.AUTOCREATED'])
    current_config = cluster.get(name, {}).get('configName')
    candidates = set(config for config in dedicated if config in configs)
    if current_config:
        candidates.add(current_config)
    shared = [key for key, value in cluster.items()
              if key != name and value.get('configName') in candidates]
    if shared:
        raise ValueError('Refusing to recreate configset used by other collections: ' + ', '.join(shared))
    if name not in collections and candidates and not recreate:
        raise ValueError('dq_demo configset already exists without its collection; use --recreate_collection')
    if name in collections:
        get_json(base, 'admin/collections', connection=connection, action='DELETE', name=name, wt='json')
    for config_name in sorted(candidates):
        if config_name in configs:
            get_json(base, 'admin/configs', connection=connection, action='DELETE', name=config_name, wt='json')
    # Let Solr copy _default to dq_demo.AUTOCREATED. This is the normal unsecured
    # SolrCloud creation path and avoids the trusted ConfigSets CREATE restriction.
    get_json(base, 'admin/collections', connection=connection, action='CREATE', name=name,
             numShards=1, replicationFactor=1, wt='json')
    return True


def describe_data_file(directory='.'):
    """Read file statistics without parsing JSON or contacting Solr."""
    path = os.path.abspath(os.path.join(directory, 'documents_solr.json'))
    print('\nData file: ' + path)
    try:
        info = os.stat(path)
    except OSError as error:
        if error.errno == errno.ENOENT:
            print('Exists: no')
            print('Generate it first with ./generate_test_data_solr.py --rows 1000')
        else:
            print('Status: could not inspect file ({0})'.format(error))
        return
    print('Exists: yes, Readable: ' + ('yes' if os.access(path, os.R_OK) else 'no'))
    if not stat.S_ISREG(info.st_mode):
        print('Status: not a regular file; cannot submit')
        return
    try:
        lines = 0
        last = b''
        with open(path, 'rb') as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                lines += chunk.count(b'\n')
                last = chunk[-1:]
        if last and last != b'\n':
            lines += 1
        print('Size: {0:,} lines, {1:,} bytes'.format(lines, info.st_size))
    except OSError as error:
        print('Size: lines unavailable ({0}), {1:,} bytes'.format(error, info.st_size))
    print('Last modified: ' + time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(info.st_mtime)))
    print('JSON contents are not validated until submission.')


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='submit_to_solr.py',
        description=__doc__,
        epilog='Uses the server and authentication settings from ../dq.ini. The ../dq.ini collection setting is ignored: this loader always uses dq_demo.')
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--submit', action='store_true',
                         help='submit documents in documents_solr.json, creating the demo collection dq_demo if needed')
    actions.add_argument('--recreate_collection', '--recreate_index',
                        dest='recreate_collection', action='store_true',
                        help='delete dq_demo and its configset, then rebuild an empty collection without submitting')
    actions.add_argument('--recreate-collection', dest='recreate_collection', action='store_true',
                         help=argparse.SUPPRESS)
    actions.add_argument('--recreate-index', dest='recreate_collection', action='store_true',
                         help=argparse.SUPPRESS)
    parser.add_argument('--preserve_empty_strings', action='store_true',
                        help='preserve empty strings for special tests; default: normal Solr blank removal')
    parser.add_argument('--preserve-empty-strings', dest='preserve_empty_strings', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--data_files_dir', default='.',
                        help='directory containing documents_solr.json (default: current directory; relative or absolute path)')
    parser.add_argument('--data-files-dir', dest='data_files_dir', help=argparse.SUPPRESS)
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        describe_data_file()
        return 0
    args = parser.parse_args(argv)
    documents = None
    if args.submit:
        # Read and validate the fixture before any destructive recreation.
        with open(os.path.join(args.data_files_dir, 'documents_solr.json'), encoding='utf-8') as stream:
            documents = json.load(stream)
        if not isinstance(documents, list) or any(not isinstance(d, dict) or not isinstance(d.get('id'), str) or not d['id'] for d in documents):
            parser.error('documents_solr.json must contain documents with nonempty string IDs')
        if len(set(d['id'] for d in documents)) != len(documents):
            parser.error('documents_solr.json contains duplicate IDs')
    config = load_config()
    try:
        base = solr_base(config)
    except ValueError as error:
        parser.error(str(error))
    if urlsplit(base).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Demo loader requires a localhost Solr target')
    cert = config.trust_certificate
    if cert and not os.path.isabs(cert):
        cert = os.path.join(os.path.dirname(config.source), cert)
    connection = Connection(config.username, config.password, cert)
    created = prepare_collection(base, connection, args.recreate_collection)
    target = base + '/dq_demo'
    validate_dynamic_fields(target, connection)
    def post(path, payload):
        request = Request(target + '/' + path, data=json.dumps(payload).encode('utf-8'),
                          headers={'Content-Type':'application/json'})
        with connection.open(request) as response:
            return json.loads(response.read().decode('utf-8'))
    # Never change a shared or unrelated configset through the demo endpoint.
    cluster = get_json(base, 'admin/collections', connection=connection, action='CLUSTERSTATUS', wt='json')['cluster']['collections']
    config_name = cluster['dq_demo'].get('configName')
    if config_name not in ('dq_demo', 'dq_demo.AUTOCREATED') or any(
            key != 'dq_demo' and value.get('configName') == config_name for key, value in cluster.items()):
        raise ValueError('Blank processing requires a dedicated dq_demo configset')
    processor = 'solr.LogUpdateProcessorFactory' if args.preserve_empty_strings else 'solr.RemoveBlankFieldUpdateProcessorFactory'
    post('config', {'update-updateprocessor': {'name': 'remove-blank', 'class': processor}})
    print('Empty strings: ' + ('preserved (special test mode)' if args.preserve_empty_strings else 'removed (normal Solr processing)'))
    if not args.submit:
        print('Recreated empty collection: ' + target)
        return 0
    total = len(documents)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        endpoint = 'update?commit=true' if end == total else 'update'
        post(endpoint, documents[start:end])
        if end == total or end % 50000 == 0:
            print('Submitted {0:,} / {1:,} records'.format(end, total), flush=True)
    count = get_json(target, 'select', connection=connection, q='*:*', rows=0, wt='json')['response']['numFound']
    if created and count != len(documents):
        raise ValueError('Demo document count does not match fixture')
    print('Submitted {0} documents to {1}; collection now contains {2} documents.'.format(len(documents), target, count))


if __name__ == '__main__':
    main()
