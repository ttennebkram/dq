"""Dispatch common read-only operations to Solr or Elasticsearch/OpenSearch."""
from urllib.parse import urlsplit


def is_solr_target(target):
    """Recognize the standard Solr URL layout used by DQ configuration."""
    parsed = urlsplit(target)
    if not parsed.scheme:
        return True
    parts = [part.lower() for part in parsed.path.split('/') if part]
    return 'solr' in parts or 'solr' in (parsed.hostname or '').lower()


def engine_name(target):
    return 'Solr' if is_solr_target(target) else 'Elasticsearch/OpenSearch'


def list_fields(target, include_counts=True, connection=None):
    if is_solr_target(target):
        from dq.solr import list_fields as implementation
    else:
        from dq.elasticsearch import list_fields as implementation
    return implementation(target, include_counts=include_counts, connection=connection)


def list_collections(target, connection=None):
    """List Solr collections or Elasticsearch/OpenSearch indexes."""
    if is_solr_target(target):
        from dq.solr import list_collections as implementation
    else:
        from dq.elasticsearch import list_indexes as implementation
    return implementation(target, connection=connection)


def collection_document_count(target, connection=None):
    if is_solr_target(target):
        from dq.solr import collection_document_count as implementation
    else:
        from dq.elasticsearch import collection_document_count as implementation
    return implementation(target, connection=connection)


def field_document_count(target, field_name, connection=None):
    if is_solr_target(target):
        from dq.solr import field_document_count as implementation
    else:
        from dq.elasticsearch import field_document_count as implementation
    return implementation(target, field_name, connection=connection)
