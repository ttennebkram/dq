"""Small standard-library client for the Solr APIs used by DQ."""
import json
from fnmatch import fnmatchcase
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request
from dq.connection import Connection


class SolrError(RuntimeError):
    """A Solr request could not be completed."""


def get_json(collection_url, path, connection=None, **parameters):
    """Get a JSON response from an API below a Solr collection URL."""
    url = '{0}/{1}'.format(collection_url.rstrip('/'), path.lstrip('/'))
    if parameters:
        url = '{0}?{1}'.format(url, urlencode(parameters))
    request = Request(url, headers={'Accept': 'application/json'})
    if connection is None:
        connection = Connection()
    try:
        with connection.open(request) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        detail = '' if connection and connection.authenticated else error.read().decode('utf-8', errors='replace').strip()
        message = 'Solr returned HTTP {0} for {1}'.format(error.code, url)
        if detail:
            message = '{0}: {1}'.format(message, detail)
        raise SolrError(message) from error
    except URLError as error:
        raise SolrError('Could not connect to {0}: {1}'.format(url, error.reason)) from error
    except OSError as error:
        raise SolrError('Could not read {0}: {1}'.format(url, error)) from error
    except (ValueError, UnicodeDecodeError) as error:
        raise SolrError('Solr returned an invalid JSON response from {0}'.format(url)) from error


def field_document_count(collection_url, field_name, connection=None):
    """Count documents containing a field, including point and vector fields."""
    response = get_json(collection_url, 'select', connection=connection, q='*:*',
                        fq='{!frange l=1}exists($dq_field)', dq_field=field_name, rows=0, wt='json')
    result = response.get('response')
    count = result.get('numFound') if isinstance(result, dict) else None
    if not isinstance(count, int):
        raise SolrError(
            'Solr response did not contain a document count for field {0!r}'.format(field_name))
    return count


def collection_document_count(collection_url, connection=None):
    """Return the number of active documents in a collection."""
    response = get_json(collection_url, 'select', connection=connection, q='*:*', rows=0, wt='json')
    result = response.get('response')
    count = result.get('numFound') if isinstance(result, dict) else None
    if not isinstance(count, int):
        raise SolrError('Solr response did not contain a collection document count')
    return count


def list_fields(collection_url, *, include_counts=True, connection=None):
    """Return concrete index fields enriched with their schema properties."""
    schema_response = get_json(collection_url, 'schema/fields', connection=connection,
                               includeDynamic='true', showDefaults='true', wt='json')
    definitions = schema_response.get('fields')
    if not isinstance(definitions, list):
        raise SolrError('Solr Schema API response did not contain a fields list')
    luke_response = get_json(collection_url, 'admin/luke', connection=connection, numTerms=0, wt='json')
    concrete_fields = luke_response.get('fields')
    if not isinstance(concrete_fields, dict):
        raise SolrError('Solr Luke API response did not contain a fields object')
    by_name = {str(field.get('name')): field for field in definitions}
    dynamic = [field for field in definitions if '*' in str(field.get('name', ''))]
    result = []
    for name, luke_properties in concrete_fields.items():
        definition = by_name.get(name)
        if definition is None:
            matches = [field for field in dynamic if fnmatchcase(name, str(field.get('name', '')))]
            definition = max(matches, key=lambda field: len(
                str(field.get('name', '')).replace('*', '')), default={})
        field = dict(definition)
        schema_name = str(field.get('name', ''))
        field['name'] = name
        field['schemaField'] = schema_name if schema_name != name else ''
        if isinstance(luke_properties, dict):
            field['documents'] = luke_properties.get('docs', '')
            field.setdefault('type', luke_properties.get('type', ''))
        if include_counts and field.get('documents', '') == '':
            field['documents'] = field_document_count(collection_url, name, connection=connection)
        result.append(field)
    return sorted(result, key=lambda field: str(field.get('name', '')))


def missing_id_pages(collection_url, field_name, *, page_size=1000, connection=None):
    """Yield bounded pages of unique keys for documents where exists(field) is false."""
    if page_size < 1:
        raise ValueError('page_size must be positive')
    key = get_json(collection_url, 'schema/uniquekey', connection=connection, wt='json').get('uniqueKey')
    if not isinstance(key, str) or not key:
        raise SolrError('Solr schema has no unique key; cannot export IDs')
    cursor = '*'
    while True:
        page = get_json(collection_url, 'select', connection=connection, q='*:*', fq='{!frange l=0 u=0}exists($dq_field)', dq_field=field_name, fl=key, sort='{0} asc'.format(
            key), rows=page_size, cursorMark=cursor, wt='json', omitHeader='false', **{'shards.tolerant': 'false'})
        header = page.get('responseHeader', {})
        if header.get('partialResults') not in (None, False, 'false'):
            raise SolrError('Solr returned partial results; ID export is incomplete')
        if header.get('status', 0) != 0 or 'error' in page:
            raise SolrError('Solr returned an error; ID export is incomplete')
        result = page.get('response')
        docs = result.get('docs') if isinstance(result, dict) else None
        next_cursor = page.get('nextCursorMark')
        if not isinstance(docs, list) or not isinstance(next_cursor, str):
            raise SolrError(
                'Solr response is missing documents or nextCursorMark; ID export is incomplete')
        ids = []
        for doc in docs:
            value = doc.get(key) if isinstance(doc, dict) else None
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise SolrError(
                    'Document has no usable unique key {0!r}; ID export is incomplete'.format(key))
            value = str(value)
            if '\n' in value or '\r' in value:
                raise SolrError('An ID contains a line break and cannot be exported one per line')
            ids.append(value)
        if next_cursor == cursor:
            if ids:
                raise SolrError(
                    'Solr cursor did not advance despite returning IDs; export is incomplete')
            return
        yield ids
        cursor = next_cursor
