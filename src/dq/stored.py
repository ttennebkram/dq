"""Bounded, read-only scans of selected stored values."""
import json
from dq.field_selection import select_fields
from dq.limits import row_limit as validate_rows
from dq.solr import get_json, list_fields, SolrError


def fields(target, include=(), exclude=(), connection=None):
    selected = [f for f in select_fields(list_fields(target, include_counts=False, connection=connection),
                                       include=include, exclude=exclude) if f.get('stored') is True]
    if not selected:
        raise SolrError('no stored fields selected; adjust include/exclude field patterns')
    return selected


def values(target, selected, connection=None, page_size=1000, include_null=False, progress=None,
           row_limit=-1, presence_only=False, scan_progress=None):
    """Yield values from at most row_limit documents, expanding all their fields.

    presence_only returns exists(field) booleans without fetching stored arrays.
    """
    row_limit = validate_rows(row_limit)
    if page_size < 1:
        raise ValueError('page_size must be positive')
    if row_limit == 0:
        return
    names = [f['name'] for f in selected]
    documents = 0
    if scan_progress:
        scan_progress.start(names)
    try:
        key = get_json(target, 'schema/uniquekey', connection=connection, wt='json').get('uniqueKey')
        if not isinstance(key, str) or not key:
            raise SolrError('Solr schema has no usable unique key')
        # Aliases avoid wildcard expansion in fl for concrete field names.
        expressions = ['exists({0})'.format(name) for name in names] if presence_only else names
        fl = ['dq_key:' + key] + ['dq_value{0}:{1}'.format(i, value) for i, value in enumerate(expressions)]
        cursor = '*'
        while row_limit == -1 or documents < row_limit:
            requested = page_size if row_limit == -1 else min(page_size, row_limit - documents)
            if progress:
                progress('fetching', documents)
            page = get_json(target, 'select', connection=connection, q='*:*', fl=','.join(fl),
                            sort=key + ' asc', cursorMark=cursor, rows=requested, wt='json',
                            omitHeader='false', **{'shards.tolerant': 'false'})
            header = page.get('responseHeader', {})
            if header.get('partialResults') not in (None, False, 'false') or header.get('status', 0) != 0 or 'error' in page:
                raise SolrError('Solr returned partial or failed results; stored-value scan incomplete')
            docs = page.get('response', {}).get('docs')
            next_cursor = page.get('nextCursorMark')
            if not isinstance(docs, list) or not isinstance(next_cursor, str):
                raise SolrError('Solr response lacks documents or cursor; stored-value scan incomplete')
            if len(docs) > requested:
                raise SolrError('Solr returned more documents than requested; stored-value scan incomplete')
            if next_cursor == cursor:
                if docs:
                    raise SolrError('Solr cursor did not advance; stored-value scan incomplete')
                return
            for doc in docs:
                identifier = doc.get('dq_key')
                if isinstance(identifier, bool) or not isinstance(identifier, (str, int, float)):
                    raise SolrError('stored-value scan returned a document without a usable unique key')
                for i, name in enumerate(names):
                    value = doc.get('dq_value' + str(i))
                    items = value if isinstance(value, list) else [value]
                    if include_null and not items:
                        items = [None]
                    for item in items:
                        if include_null or item is not None:
                            yield str(identifier), name, item
                documents += 1
                if scan_progress:
                    scan_progress.update(documents)
            if progress:
                progress('scanned', documents)
            cursor = next_cursor
    finally:
        if scan_progress:
            scan_progress.finish(documents)


def text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def pages(rows, size=1000):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
