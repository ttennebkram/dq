"""Shared Elasticsearch/OpenSearch index creation and bounded NDJSON loading."""
import argparse
import configparser
import json
import os
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, quote
from urllib.request import Request
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from dq.config import load_config
from dq.connection import Connection


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
    # Reuse discovery, but never forward Solr credentials to a different engine.
    found = load_config(options.config)
    settings = {}
    section = None
    if found.source:
        ini = configparser.ConfigParser(interpolation=None)
        with open(found.source, encoding='utf-8') as stream:
            ini.read_file(stream)
        ini.defaults().clear()
        # One shared section for either engine. Retain older OpenSearch-only files.
        for candidate in ('elasticsearch', 'opensearch'):
            if ini.has_section(candidate):
                section = candidate
                settings = dict(ini.items(section))
                break
    for name in ('main_url', 'username', 'password', 'trust_certificate'):
        supplied = getattr(options, name)
        if supplied is not None:
            settings[name] = supplied
    url = settings.get('main_url', 'http://localhost:' + ('9201' if section == 'opensearch' else '9200'))
    parsed = urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise SubmissionError('main_url must be an HTTP(S) server root without index path or credentials')
    cert = settings.get('trust_certificate')
    if cert:
        cert = os.path.expanduser(cert)
        if options.trust_certificate is None and found.source and not os.path.isabs(cert):
            cert = os.path.join(os.path.dirname(found.source), cert)
    return url.rstrip('/'), Connection(settings.get('username'), settings.get('password'), cert), found.source, section


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
    prog = 'submit-to-es.py'
    parser = argparse.ArgumentParser(prog=prog, description='Create an index and submit test data to Elasticsearch or OpenSearch. The same command, schema and bulk format support both.',
        epilog='Reads [elasticsearch] in dq.ini for either engine. A legacy [opensearch] section is used only when [elasticsearch] is absent. For the local OpenSearch instance: --main_url http://localhost:9201. No engine switch is needed.')
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--submit', action='store_true', help='create index if needed and add/replace matching IDs')
    actions.add_argument('--recreate_index', '--recreate-index', action='store_true', help='delete the target index, recreate mappings, and submit')
    parser.add_argument('--data_files_dir', '--data-files-dir', default='.', help='directory containing documents-es.ndjson; default: cwd')
    parser.add_argument('--index', default='dq-demo', help='target index (default: dq-demo)')
    parser.add_argument('--config', help='INI file; otherwise discover dq.ini in cwd/parents')
    parser.add_argument('--main_url', '--main-url', help='Elasticsearch or OpenSearch server root; overrides INI main_url; default: http://localhost:9200')
    for name in ('username','password','trust_certificate'):
        parser.add_argument('--' + name, help='override the shared [elasticsearch] INI setting')
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        path = os.path.abspath('documents-es.ndjson')
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
        if not re.match(r'^[a-z0-9][a-z0-9_-]*$', args.index):
            raise SubmissionError('index must use lowercase letters, digits, hyphens, and underscores')
        path = os.path.join(args.data_files_dir, 'documents-es.ndjson')
        total = sum(count for _,count in batches(path))  # Validate before destructive requests.
        with open(os.path.join(os.path.dirname(__file__), 'schema-es.json'), encoding='utf-8') as stream:
            schema = json.load(stream)
        base, connection, config, section = connection_settings(args)
        identity = request(connection, base, '/')
        actual, version = server_identity(identity)
        print('Target: {0}/{1} ({2} {3})'.format(base,args.index,actual,version))
        if config:
            origin = 'section [{0}]'.format(section) if section else 'no ES/OpenSearch section; using CLI/defaults'
            print('Configuration: {0}, {1}'.format(config,origin))
        index_path = '/' + quote(args.index, safe='')
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
