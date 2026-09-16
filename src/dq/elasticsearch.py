"""Small standard-library Elasticsearch/OpenSearch client used by DQ."""
import json
from fnmatch import fnmatchcase
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request
from dq.connection import Connection
from dq.solr import SolrError


class ElasticsearchError(SolrError):
    """An Elasticsearch/OpenSearch request could not be completed."""


def _request_json(url, connection=None, method='GET', body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {'Accept': 'application/json'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=data, headers=headers, method=method)
    if connection is None:
        connection = Connection()
    try:
        with connection.open(request) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        detail = '' if connection and connection.authenticated else error.read().decode(
            'utf-8', errors='replace').strip()
        message = 'Elasticsearch/OpenSearch returned HTTP {0} for {1}'.format(error.code, url)
        if detail:
            message = '{0}: {1}'.format(message, detail)
        raise ElasticsearchError(message) from error
    except URLError as error:
        raise ElasticsearchError('Could not connect to {0}: {1}'.format(url, error.reason)) from error
    except OSError as error:
        raise ElasticsearchError('Could not read {0}: {1}'.format(url, error)) from error
    except (ValueError, UnicodeDecodeError) as error:
        raise ElasticsearchError(
            'Elasticsearch/OpenSearch returned invalid JSON from {0}'.format(url)) from error


def request_json(index_url, path, connection=None, method='GET', body=None, **parameters):
    url = '{0}/{1}'.format(index_url.rstrip('/'), path.lstrip('/'))
    if parameters:
        url = '{0}?{1}'.format(url, urlencode(parameters))
    return _request_json(url, connection=connection, method=method, body=body)


def _cluster_url(index_url):
    parsed = urlsplit(index_url.rstrip('/'))
    path = parsed.path.rsplit('/', 1)[0]
    return urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))


def _source_allowed(name, source):
    if source is False or (isinstance(source, dict) and source.get('enabled') is False):
        return False
    if not isinstance(source, dict):
        return True
    includes = source.get('includes', source.get('include'))
    excludes = source.get('excludes', source.get('exclude'))
    if isinstance(includes, str):
        includes = [includes]
    if isinstance(excludes, str):
        excludes = [excludes]
    if includes and not any(fnmatchcase(name, pattern) for pattern in includes):
        return False
    if excludes and any(fnmatchcase(name, pattern) for pattern in excludes):
        return False
    return True


def _type_class(field_type):
    if field_type in ('text', 'match_only_text'):
        return 'elasticsearch.TextField'
    if field_type in ('keyword', 'constant_keyword', 'wildcard'):
        return 'elasticsearch.StrField'
    if field_type in ('date', 'date_nanos'):
        return 'elasticsearch.DatePointField'
    if field_type in ('dense_vector', 'knn_vector'):
        return 'elasticsearch.DenseVectorField'
    return 'elasticsearch.Field'


def _doc_values_default(field_type):
    return field_type not in ('text', 'match_only_text', 'object', 'nested',
                              'binary', 'dense_vector', 'semantic_text')


def _flatten(properties, source, prefix=''):
    fields = []
    if not isinstance(properties, dict):
        return fields
    for short_name in sorted(properties):
        mapping = properties[short_name]
        if not isinstance(mapping, dict):
            continue
        name = prefix + short_name
        children = mapping.get('properties')
        if isinstance(children, dict):
            fields.extend(_flatten(children, source, name + '.'))
            continue
        field_type = str(mapping.get('type', 'object'))
        source_value = _source_allowed(name, source)
        individually_stored = mapping.get('store') is True
        fields.append({
            'name': name,
            'type': field_type,
            'typeClass': _type_class(field_type),
            'stored': source_value or individually_stored,
            'retrieval': 'source' if source_value else ('stored' if individually_stored else ''),
            'indexed': mapping.get('index', True) is not False,
            'docValues': mapping.get('doc_values', _doc_values_default(field_type)) is not False,
            # Elasticsearch mappings do not distinguish scalar values from arrays.
            'multiValued': None,
            'schemaField': '',
            'engine': 'elasticsearch',
        })
    return fields


def list_fields(index_url, include_counts=True, connection=None):
    """Return source/stored leaf fields from an index mapping.

    Mapping multi-fields are deliberately omitted because they do not represent
    separate values in _source.
    """
    response = request_json(index_url, '_mapping', connection=connection)
    if not isinstance(response, dict) or not response:
        raise ElasticsearchError('mapping response did not contain an index mapping')
    merged = {}
    for index_name, index in response.items():
        mappings = index.get('mappings') if isinstance(index, dict) else None
        if not isinstance(mappings, dict):
            raise ElasticsearchError('mapping for {0!r} is invalid'.format(index_name))
        source = mappings.get('_source', {})
        for field in _flatten(mappings.get('properties', {}), source):
            existing = merged.get(field['name'])
            if existing is not None and existing['type'] != field['type']:
                existing['type'] = 'conflict: {0}, {1}'.format(existing['type'], field['type'])
                existing['typeClass'] = ''
            else:
                merged[field['name']] = field
    result = []
    for name in sorted(merged):
        field = merged[name]
        if include_counts:
            field['documents'] = field_document_count(index_url, name, connection=connection)
        result.append(field)
    return result


def collection_document_count(index_url, connection=None):
    response = request_json(index_url, '_count', connection=connection)
    count = response.get('count') if isinstance(response, dict) else None
    if isinstance(count, bool) or not isinstance(count, int):
        raise ElasticsearchError('count response did not contain a document count')
    return count


def field_document_count(index_url, field_name, connection=None):
    response = request_json(index_url, '_count', connection=connection, method='POST',
                            body={'query': {'exists': {'field': field_name}}})
    count = response.get('count') if isinstance(response, dict) else None
    if isinstance(count, bool) or not isinstance(count, int):
        raise ElasticsearchError(
            'count response did not contain a document count for field {0!r}'.format(field_name))
    return count


_MISSING = object()


def _source_value(value, parts):
    if not parts:
        return value
    if isinstance(value, list):
        result = []
        for item in value:
            found = _source_value(item, parts)
            if found is _MISSING:
                continue
            result.extend(found if isinstance(found, list) else [found])
        return result if result else _MISSING
    if not isinstance(value, dict) or parts[0] not in value:
        return _MISSING
    return _source_value(value[parts[0]], parts[1:])


def _hits(response):
    if not isinstance(response, dict):
        raise ElasticsearchError('search response was not a JSON object')
    shards = response.get('_shards', {})
    if isinstance(shards, dict) and shards.get('failed', 0):
        raise ElasticsearchError('search returned failed shards; stored-value scan incomplete')
    hits = response.get('hits', {}).get('hits')
    if not isinstance(hits, list):
        raise ElasticsearchError('search response did not contain a hits list')
    return hits


def values(index_url, selected, connection=None, page_size=1000, include_null=False,
           row_limit=-1, presence_only=False, scan_progress=None):
    """Yield selected values using a bounded Elasticsearch/OpenSearch scroll."""
    if page_size < 1:
        raise ValueError('page_size must be positive')
    if row_limit == 0:
        return
    names = [field['name'] for field in selected]
    source_names = [field['name'] for field in selected if field.get('retrieval') == 'source']
    stored_names = [field['name'] for field in selected if field.get('retrieval') == 'stored']
    size = page_size if row_limit == -1 else min(page_size, row_limit)
    body = {'query': {'match_all': {}}, 'size': size, 'sort': ['_doc'],
            '_source': source_names if source_names else False}
    if stored_names:
        body['stored_fields'] = stored_names
    documents = 0
    scroll_id = None
    if scan_progress:
        scan_progress.start(names)
    try:
        response = request_json(index_url, '_search', connection=connection, method='POST',
                                body=body, scroll='1m')
        while True:
            scroll_id = response.get('_scroll_id', scroll_id) if isinstance(response, dict) else scroll_id
            hits = _hits(response)
            if not hits:
                return
            for hit in hits:
                if row_limit != -1 and documents >= row_limit:
                    return
                identifier = hit.get('_id') if isinstance(hit, dict) else None
                if not isinstance(identifier, str) or not identifier:
                    raise ElasticsearchError('stored-value scan returned a document without _id')
                source = hit.get('_source', {}) if isinstance(hit.get('_source', {}), dict) else {}
                stored_values = hit.get('fields', {}) if isinstance(hit.get('fields', {}), dict) else {}
                for field in selected:
                    name = field['name']
                    if field.get('retrieval') == 'stored':
                        value = stored_values.get(name, _MISSING)
                    else:
                        value = _source_value(source, name.split('.'))
                    if presence_only:
                        yield identifier, name, value is not _MISSING and value is not None and value != []
                        continue
                    if value is _MISSING:
                        value = None
                    items = value if isinstance(value, list) else [value]
                    if include_null and not items:
                        items = [None]
                    for item in items:
                        if include_null or item is not None:
                            yield identifier, name, item
                documents += 1
                if scan_progress:
                    scan_progress.update(documents)
            if not scroll_id:
                raise ElasticsearchError('search response lacked a scroll ID; scan incomplete')
            response = _request_json(_cluster_url(index_url).rstrip('/') + '/_search/scroll',
                                     connection=connection, method='POST',
                                     body={'scroll': '1m', 'scroll_id': scroll_id})
    finally:
        if scroll_id:
            try:
                _request_json(_cluster_url(index_url).rstrip('/') + '/_search/scroll',
                              connection=connection, method='DELETE',
                              body={'scroll_id': [scroll_id]})
            except ElasticsearchError:
                pass
        if scan_progress:
            scan_progress.finish(documents)
