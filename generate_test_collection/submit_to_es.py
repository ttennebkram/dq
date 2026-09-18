#!/usr/bin/env python3
"""Create an Elasticsearch/OpenSearch index and submit bounded NDJSON batches."""
import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, quote
from urllib.request import Request
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from dq.config import load_config
from dq.connection import Connection
from dq.search import is_solr_target

TARGET_INDEX = 'dq_demo'


class SubmissionError(ValueError):
    pass


def request(connection, base, path, method='GET', payload=None, ndjson=False, allow_missing=False):
    data = payload if ndjson else (json.dumps(payload).encode('utf-8') if payload is not None else None)
    req = Request(base.rstrip('/') + path, data=data, method=method,
                  headers={'Accept':'application/json', 'Content-Type':'application/x-ndjson' if ndjson else 'application/json'})
    try:
        with connection.open(req) as response:
            body = response.read()
            return json.loads(body.decode('utf-8')) if body else {}
    except HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise SubmissionError('HTTP {0} during {1} {2}'.format(error.code, method, path))


def batches(path, max_records=500, max_bytes=5 * 1024 * 1024):
    """Validate paired index/source lines and keep bulk requests bounded."""
    batch, size, count = [], 0, 0
    with open(path, 'rb') as stream:
        line = 0
        while True:
            action = stream.readline(max_bytes + 1)
            if not action:
                break
            source = stream.readline(max_bytes + 1)
            line += 2
            if not action.endswith(b'\n') or not source.endswith(b'\n'):
                raise SubmissionError('NDJSON requires paired, newline-terminated lines (near line {0})'.format(line))
            if len(action) + len(source) > max_bytes:
                raise SubmissionError('A document exceeds the bulk size limit')
            try:
                metadata, document = json.loads(action.decode('utf-8')), json.loads(source.decode('utf-8'))
            except (ValueError, UnicodeError):
                raise SubmissionError('Invalid UTF-8 JSON near line {0}'.format(line))
            if not isinstance(metadata, dict) or set(metadata) != {'index'}:
                raise SubmissionError('Only index actions are allowed')
            entry = metadata['index']
            if not isinstance(entry, dict) or set(entry) != {'_id'} or not isinstance(entry['_id'], str) or not entry['_id']:
                raise SubmissionError('Each index action must contain only a nonempty string _id')
            if len(entry['_id'].encode('utf-8')) > 512:
                raise SubmissionError('Document ID exceeds the shared 512-byte limit')
            if not isinstance(document, dict) or document.get('id') != entry['_id']:
                raise SubmissionError('Source id must match action _id')
            if batch and (count >= max_records or size + len(action) + len(source) > max_bytes):
                yield b''.join(batch), count
                batch, size, count = [], 0, 0
            batch.extend([action, source])
            size += len(action) + len(source)
            count += 1
        if batch:
            yield b''.join(batch), count


def check_bulk(response, count):
    items = response.get('items')
    if not isinstance(items, list) or len(items) != count:
        raise SubmissionError('Bulk response is incomplete')
    failed = []
    for item in items:
        result = item.get('index', {}) if isinstance(item, dict) else {}
        if result.get('status') not in (200, 201) or 'error' in result:
            failed.append(str(result.get('_id', 'unknown')))
    if response.get('errors') or failed:
        raise SubmissionError('Bulk indexing failed; partial data may exist. Failed IDs: ' + ', '.join(failed[:5]))


def connection_settings(options):
    # Reuse the normal DQ target only when it is already an ES/OpenSearch URL.
    # Never forward credentials saved for Solr to a different engine.
    found = load_config(options.config)
    settings = {}
    source = None
    if found.main_url and is_solr_target(found.main_url) and options.main_url is None:
        raise SubmissionError(
            'dq.ini main_url identifies Solr; submit_to_es.py requires an Elasticsearch/OpenSearch URL')
    if found.main_url and not is_solr_target(found.main_url):
        source = 'DQ target settings'
        settings = dict((name, getattr(found, name)) for name in (
            'main_url', 'username', 'password', 'trust_certificate')
                        if getattr(found, name) is not None)
    for name in ('main_url', 'username', 'password', 'trust_certificate'):
        supplied = getattr(options, name)
        if supplied is not None:
            settings[name] = supplied
    url = settings.get('main_url', 'http://localhost:9200')
    parsed = urlsplit(url)
    if is_solr_target(url):
        raise SubmissionError('submit_to_es.py requires an Elasticsearch/OpenSearch URL, not a Solr URL')
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise SubmissionError('main_url must be an HTTP(S) server root without index path or credentials')
    cert = settings.get('trust_certificate')
    if cert:
        cert = os.path.expanduser(cert)
        if options.trust_certificate is None and found.source and not os.path.isabs(cert):
            cert = os.path.join(os.path.dirname(found.source), cert)
    return url.rstrip('/'), Connection(settings.get('username'), settings.get('password'), cert), found.source, source


def server_identity(identity):
    """Recognize either engine before any index changes."""
    if not isinstance(identity, dict):
        raise SubmissionError('Server is not recognized as Elasticsearch or OpenSearch')
    version = identity.get('version', {})
    if not isinstance(version, dict) or not version.get('number'):
        raise SubmissionError('Server did not return an Elasticsearch/OpenSearch version')
    if version.get('distribution') == 'opensearch':
        return 'OpenSearch', version['number']
    if identity.get('tagline') == 'You Know, for Search':
        return 'Elasticsearch', version['number']
    raise SubmissionError('Server is not recognized as Elasticsearch or OpenSearch')


def main(argv=None):
    prog = 'submit_to_es.py'
    parser = argparse.ArgumentParser(prog=prog, description='Create the fixed dq_demo index and submit test data to Elasticsearch or OpenSearch. The same command, schema and bulk format support both.',
        epilog='Uses the server and authentication settings from ../dq.ini when main_url identifies Elasticsearch or OpenSearch. The ../dq.ini collection/index setting is ignored: this loader always uses dq_demo. For a different server, use --main_url or a separate DQ configuration file. No engine switch is needed.')
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--submit', action='store_true', help='submit documents in documents_es.ndjson, creating the demo index dq_demo if needed')
    actions.add_argument('--recreate_index', action='store_true', help='delete the target index and recreate its mappings without submitting')
    actions.add_argument('--recreate-index', dest='recreate_index', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--data_files_dir', default='.', help='directory containing documents_es.ndjson; default: cwd')
    parser.add_argument('--data-files-dir', dest='data_files_dir', help=argparse.SUPPRESS)
    parser.add_argument('--config', help='INI file; otherwise discover dq.ini in cwd/parents')
    parser.add_argument('--main_url', '--main-url', help='Elasticsearch or OpenSearch server root; overrides INI main_url; default: http://localhost:9200')
    for name in ('username','password','trust_certificate'):
        parser.add_argument('--' + name, help='override the normal DQ connection setting')
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        path = os.path.abspath('documents_es.ndjson')
        print('\nData file: ' + path)
        print('Exists: {0}, Readable: {1}'.format('yes' if os.path.isfile(path) else 'no','yes' if os.access(path, os.R_OK) else 'no'))
        if os.path.isfile(path) and os.access(path, os.R_OK):
            info = os.stat(path)
            with open(path, 'rb') as stream:
                lines = sum(1 for line in stream)
            print('Size: {0:,} lines, {1:,} bytes'.format(lines, info.st_size))
            print('Modified: ' + time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(info.st_mtime)))
        return 0
    args = parser.parse_args(argv)
    try:
        path = os.path.join(args.data_files_dir, 'documents_es.ndjson')
        total = (sum(count for _,count in batches(path))
                 if args.submit else None)  # Validate before destructive requests.
        with open(os.path.join(os.path.dirname(__file__), 'schema_es.json'), encoding='utf-8') as stream:
            schema = json.load(stream)
        base, connection, config, settings_source = connection_settings(args)
        identity = request(connection, base, '/')
        actual, version = server_identity(identity)
        print('Target: {0}/{1} ({2} {3})'.format(base,TARGET_INDEX,actual,version))
        if config:
            origin = settings_source if settings_source else 'CLI/defaults'
            print('Configuration: {0}, {1}'.format(config,origin))
        index_path = '/' + quote(TARGET_INDEX, safe='')
        existing = request(connection,base,index_path,allow_missing=True)
        if existing is not None and args.recreate_index:
            deleted = request(connection,base,index_path,method='DELETE')
            if deleted.get('acknowledged') is not True:
                raise SubmissionError('Index deletion was not acknowledged')
            existing = None
        if existing is None:
            response = request(connection,base,index_path,method='PUT',payload=schema)
            if response.get('acknowledged') is not True:
                raise SubmissionError('Index creation was not acknowledged')
        if not args.submit:
            print('Recreated empty index: {0}{1}'.format(base, index_path))
            return 0
        written = 0
        for payload,count in batches(path):
            response = request(connection,base,index_path+'/_bulk',method='POST',payload=payload,ndjson=True)
            check_bulk(response,count)
            written += count
            if written == total or written % 50000 == 0:
                print('Submitted {0:,} / {1:,} records'.format(written,total),flush=True)
        request(connection,base,index_path+'/_refresh',method='POST')
        count = request(connection,base,index_path+'/_count')['count']
        print('Complete: {0:,} records submitted; index contains {1:,} documents.'.format(written,count))
        return 0
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, 'Error: {0}\n'.format(error))


if __name__ == '__main__':
    sys.exit(main())
