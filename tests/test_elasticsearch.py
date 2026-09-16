"""Elasticsearch/OpenSearch mapping and stored-value behavior."""
import unittest
from unittest.mock import patch

from dq import elasticsearch
from dq.field_selection import is_date_field, is_text_field
from dq.search import engine_name, is_solr_target


class ElasticsearchTests(unittest.TestCase):
    def test_mapping_types_do_not_depend_on_name_suffixes(self):
        mapping = {
            'people': {
                'mappings': {
                    'properties': {
                        'displayName': {
                            'type': 'text',
                            'fields': {'exact': {'type': 'keyword'}},
                        },
                        'status': {'type': 'keyword'},
                        'created': {'type': 'date'},
                        'contact': {'properties': {
                            'emailAddress': {'type': 'keyword'},
                        }},
                    }
                }
            }
        }
        with patch('dq.elasticsearch.request_json', return_value=mapping):
            fields = elasticsearch.list_fields('http://localhost:9200/people',
                                                include_counts=False)
        by_name = dict((field['name'], field) for field in fields)
        self.assertEqual(set(by_name),
                         {'displayName', 'status', 'created', 'contact.emailAddress'})
        self.assertTrue(is_text_field(by_name['displayName']))
        self.assertTrue(is_text_field(by_name['status']))
        self.assertTrue(is_text_field(by_name['contact.emailAddress']))
        self.assertTrue(is_date_field(by_name['created']))
        self.assertNotIn('displayName.exact', by_name)
        self.assertTrue(all(field['retrieval'] == 'source' for field in fields))

    def test_source_exclusions_and_individually_stored_fields(self):
        mapping = {'items': {'mappings': {
            '_source': {'excludes': ['secret*']},
            'properties': {
                'public': {'type': 'keyword'},
                'secret': {'type': 'keyword'},
                'secret_saved': {'type': 'keyword', 'store': True},
            },
        }}}
        with patch('dq.elasticsearch.request_json', return_value=mapping):
            fields = elasticsearch.list_fields('http://localhost:9200/items',
                                                include_counts=False)
        by_name = dict((field['name'], field) for field in fields)
        self.assertEqual(by_name['public']['retrieval'], 'source')
        self.assertFalse(by_name['secret']['stored'])
        self.assertEqual(by_name['secret_saved']['retrieval'], 'stored')

    def test_counts_use_count_and_exists_query(self):
        with patch('dq.elasticsearch.request_json', side_effect=[
                {'count': 12}, {'count': 7}]) as request:
            self.assertEqual(elasticsearch.collection_document_count('http://host:9200/i'), 12)
            self.assertEqual(elasticsearch.field_document_count(
                'http://host:9200/i', 'email'), 7)
        self.assertEqual(request.call_args_list[1][1]['method'], 'POST')
        self.assertEqual(request.call_args_list[1][1]['body'],
                         {'query': {'exists': {'field': 'email'}}})

    def test_scroll_reads_source_stored_nested_array_and_missing_values(self):
        selected = [
            {'name': 'contact.email', 'retrieval': 'source'},
            {'name': 'tag', 'retrieval': 'source'},
            {'name': 'saved', 'retrieval': 'stored'},
            {'name': 'absent', 'retrieval': 'source'},
        ]
        first = {
            '_scroll_id': 'scroll-1',
            '_shards': {'failed': 0},
            'hits': {'hits': [{
                '_id': '42',
                '_source': {
                    'contact': {'email': 'person@example.com'},
                    'tag': ['one', 'two'],
                },
                'fields': {'saved': ['stored value']},
            }]},
        }
        empty = {'_scroll_id': 'scroll-1', '_shards': {'failed': 0},
                 'hits': {'hits': []}}
        with patch('dq.elasticsearch.request_json', return_value=first) as initial, \
                patch('dq.elasticsearch._request_json', side_effect=[empty, {}]) as scrolling:
            rows = list(elasticsearch.values(
                'http://localhost:9200/people', selected, include_null=True))
        self.assertEqual(rows, [
            ('42', 'contact.email', 'person@example.com'),
            ('42', 'tag', 'one'),
            ('42', 'tag', 'two'),
            ('42', 'saved', 'stored value'),
            ('42', 'absent', None),
        ])
        body = initial.call_args[1]['body']
        self.assertEqual(body['_source'], ['contact.email', 'tag', 'absent'])
        self.assertEqual(body['stored_fields'], ['saved'])
        self.assertEqual(scrolling.call_args_list[-1][1]['method'], 'DELETE')

    def test_target_dispatch_recognizes_standard_urls(self):
        self.assertTrue(is_solr_target('http://localhost:8983/solr/people'))
        self.assertFalse(is_solr_target('http://localhost:9200/people'))
        self.assertEqual(engine_name('http://localhost:9201/people'),
                         'Elasticsearch/OpenSearch')


if __name__ == '__main__':
    unittest.main()
