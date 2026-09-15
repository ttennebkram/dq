"""Export documents whose selected stored field is missing or null."""
from dq import stored
from dq.findings import Finding, CsvExport
from dq.field_selection import select_fields
from dq.solr import SolrError, list_fields


def prepare_csv(target, *, include=(), exclude=(), connection=None, row_limit=-1,
                scan_progress=None, skip_null_values=False):
    fields = [field for field in select_fields(
        list_fields(target, include_counts=False, connection=connection),
        include=include, exclude=exclude) if field.get('stored') is True]
    if not fields:
        raise SolrError('missing_fields requires stored fields; adjust include/exclude field patterns')
    def rows():
        values = stored.values(target, fields, connection, row_limit=row_limit,
                               presence_only=True, include_null=True,
                               scan_progress=scan_progress)
        for identifier, name, present in values:
            if present is False:
                yield Finding(name, (identifier, 'missing_fields: missing or null', ''))
            elif present is not True:
                raise SolrError('Solr did not return a boolean field-presence value')
    return CsvExport(fields, ['id', 'reason', 'value'], stored.pages(rows()))
