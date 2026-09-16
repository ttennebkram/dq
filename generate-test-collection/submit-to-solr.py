#!/usr/bin/env python3
"""Submit demo documents by ID; optionally recreate the local dq-demo collection."""
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
from dq.config import load_config, collection_url
from dq.connection import Connection
from dq.solr import get_json

BATCH_SIZE = 5000


def prepare_collection(base, connection, recreate=False):
    name = 'dq-demo'
    collections = get_json(base, 'admin/collections', connection=connection, action='LIST', wt='json')['collections']
    configs = get_json(base, 'admin/configs', connection=connection, action='LIST', wt='json')['configSets']
    if name in collections and not recreate:
        return False
    if name in configs:
        if not recreate:
            raise ValueError('dq-demo configset already exists without its collection; use --recreate_collection')
        status = get_json(base, 'admin/collections', connection=connection, action='CLUSTERSTATUS', wt='json')
        shared = [key for key, value in status['cluster']['collections'].items()
                  if key != name and value.get('configName') == name]
        if shared:
            raise ValueError('Refusing to recreate configset used by other collections: ' + ', '.join(shared))
    if name in collections:
        get_json(base, 'admin/collections', connection=connection, action='DELETE', name=name, wt='json')
    if name in configs:
        get_json(base, 'admin/configs', connection=connection, action='DELETE', name=name, wt='json')
    get_json(base, 'admin/configs', connection=connection, action='CREATE', name=name, baseConfigSet='_default', wt='json')
    get_json(base, 'admin/collections', connection=connection, action='CREATE', name=name,
             numShards=1, replicationFactor=1, wt='json', **{'collection.configName':name})
    return True


def describe_data_file(directory='.'):
    """Read file statistics without parsing JSON or contacting Solr."""
    path = os.path.abspath(os.path.join(directory, 'documents-solr.json'))
    print('\nData file: ' + path)
    try:
        info = os.stat(path)
    except OSError as error:
        if error.errno == errno.ENOENT:
            print('Exists: no')
            print('Generate it first with ./generate-test-data-solr.py --count 1000')
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
    parser = argparse.ArgumentParser(prog='submit-to-solr.py', description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--submit', action='store_true',
                         help='submit documents, creating the demo collection if needed; replace matching IDs')
    actions.add_argument('--recreate_collection', '--recreate-collection', action='store_true',
                        help='delete dq-demo and its configset, then rebuild and load it; removes all existing demo records')
    parser.add_argument('--preserve_empty_strings', '--preserve-empty-strings', action='store_true',
                        help='preserve empty strings for special tests; default: normal Solr blank removal')
    parser.add_argument('--data_files_dir', '--data-files-dir', default='.',
                        help='directory containing documents-solr.json (default: current directory; relative or absolute path)')
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        describe_data_file()
        return 0
    args = parser.parse_args(argv)
    # Read and validate the fixture before any destructive recreation.
    with open(os.path.join(args.data_files_dir, 'documents-solr.json'), encoding='utf-8') as stream:
        documents = json.load(stream)
    if not isinstance(documents, list) or any(not isinstance(d, dict) or not isinstance(d.get('id'), str) or not d['id'] for d in documents):
        parser.error('documents-solr.json must contain documents with nonempty string IDs')
    if len(set(d['id'] for d in documents)) != len(documents):
        parser.error('documents-solr.json contains duplicate IDs')
    setup = []
    for filename, endpoint in [('schema-solr.json', 'schema')]:
        with open(os.path.join(os.path.dirname(__file__), filename), encoding='utf-8') as stream:
            setup.append((endpoint, json.load(stream)))
    config = load_config()
    base = collection_url(config).rsplit('/', 1)[0]
    if urlsplit(base).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Demo loader requires a localhost Solr target')
    cert = config.trust_certificate
    if cert and not os.path.isabs(cert):
        cert = os.path.join(os.path.dirname(config.source), cert)
    connection = Connection(config.username, config.password, cert)
    created = prepare_collection(base, connection, args.recreate_collection)
    target = base + '/dq-demo'
    def post(path, payload):
        request = Request(target + '/' + path, data=json.dumps(payload).encode('utf-8'),
                          headers={'Content-Type':'application/json'})
        with connection.open(request) as response:
            return json.loads(response.read().decode('utf-8'))
    if created:
        for endpoint, payload in setup:
            post(endpoint, payload)
    # Never change a shared or unrelated configset through the demo endpoint.
    cluster = get_json(base, 'admin/collections', connection=connection, action='CLUSTERSTATUS', wt='json')['cluster']['collections']
    if cluster['dq-demo'].get('configName') != 'dq-demo' or any(
            key != 'dq-demo' and value.get('configName') == 'dq-demo' for key, value in cluster.items()):
        raise ValueError('Blank processing requires a dedicated dq-demo configset')
    processor = 'solr.LogUpdateProcessorFactory' if args.preserve_empty_strings else 'solr.RemoveBlankFieldUpdateProcessorFactory'
    post('config', {'update-updateprocessor': {'name': 'remove-blank', 'class': processor}})
    print('Empty strings: ' + ('preserved (special test mode)' if args.preserve_empty_strings else 'removed (normal Solr processing)'))
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
