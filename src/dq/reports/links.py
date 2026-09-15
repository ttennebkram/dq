"""Read-only source-query links; never embed connection credentials."""
from urllib.parse import urlencode
from dq.solr import presence_query


def solr_query_url(target, field=None, missing=False):
    parameters = [('q', '*:*'), ('rows', 10), ('wt', 'json')]
    if field is not None:
        vector = str(field.get('typeClass', '')).endswith('DenseVectorField')
        parameters += [('fq', presence_query(field['name'], missing=missing, function=vector)),
                       ('dq_field', field['name'])]
    return target.rstrip('/') + '/select?' + urlencode(parameters)


def source_links(target, field=None):
    links = ['[Browse documents in Solr](' + solr_query_url(target) + ')']
    if field is not None:
        links += ['[Documents with this field](' + solr_query_url(target, field) + ')',
                  '[Documents missing this field](' + solr_query_url(target, field, missing=True) + ')']
    return [' | '.join(links), '',
            'Source links show up to 10 current documents and use indexed presence; '
            'they do not reproduce Python regex or whitespace findings. CSV links contain the recorded findings.', '']
