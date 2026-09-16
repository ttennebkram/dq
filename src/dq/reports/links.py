"""Read-only source-query links; never embed connection credentials."""
import re
from urllib.parse import urlencode
from dq.solr import presence_query
from dq.search import is_solr_target, engine_name


def solr_query_url(target, field=None, missing=False):
    parameters = [('q', '*:*'), ('rows', 10), ('wt', 'json')]
    if field is not None:
        vector = str(field.get('typeClass', '')).endswith('DenseVectorField')
        parameters += [('fq', presence_query(field['name'], missing=missing, function=vector)),
                       ('dq_field', field['name'])]
    return target.rstrip('/') + '/select?' + urlencode(parameters)


def elasticsearch_query_url(target, field=None, missing=False):
    query = '*:*'
    if field is not None:
        escaped = re.sub(r'([+\-=!(){}\[\]^"~*?:\\/])', r'\\\1', field['name'])
        query = '_exists_:' + escaped
        if missing:
            query = 'NOT ' + query
    return target.rstrip('/') + '/_search?' + urlencode([('q', query), ('size', 10)])


def query_url(target, field=None, missing=False):
    return (solr_query_url(target, field, missing) if is_solr_target(target)
            else elasticsearch_query_url(target, field, missing))


def source_links(target, field=None):
    links = ['[Browse documents in {0}]({1})'.format(engine_name(target), query_url(target))]
    if field is not None:
        links += ['[Documents with this field](' + query_url(target, field) + ')',
                  '[Documents missing this field](' + query_url(target, field, missing=True) + ')']
    return [' | '.join(links), '',
            'Source links show up to 10 current documents and use field presence; '
            'they do not reproduce Python regex or whitespace findings. CSV links contain the recorded findings.', '']
