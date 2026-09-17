"""Presence queries must support analyzed text as well as dense vectors."""
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from dq.solr import SolrError, field_document_count, missing_id_pages


def failure(code):
    error = SolrError('query failed')
    error.__cause__ = HTTPError('http://solr/c', code, 'failed', {}, None)
    return error


class PresenceTests(unittest.TestCase):
    def test_text_presence_and_escaped_field_names(self):
        with patch('dq.solr.get_json', return_value={'response': {'numFound': 7}}) as get:
            self.assertEqual(field_document_count('url', 'name:part t'), 7)
            self.assertEqual(get.call_args[1]['fq'], '{!lucene}name\\:part\\ t:*')

    def test_vector_fallback(self):
        with patch('dq.solr.get_json', side_effect=[failure(400), {'response': {'numFound': 9}}]) as get:
            self.assertEqual(field_document_count('url', 'vector'), 9)
            self.assertEqual(get.call_args[1]['fq'], '{!frange l=1}exists($dq_field)')

    def test_other_errors_and_failed_fallback_propagate(self):
        for responses in ([failure(500)], [failure(401)], [failure(400), failure(400)]):
            with patch('dq.solr.get_json', side_effect=responses) as get:
                with self.assertRaises(SolrError):
                    field_document_count('url', 'field')
                self.assertEqual(get.call_count, len(responses))

    def test_vector_csv_remembers_fallback_across_pages(self):
        responses = [{'uniqueKey': 'id'}, failure(400),
                     {'response': {'docs': [{'id': 'a'}]}, 'nextCursorMark': 'next'},
                     {'response': {'docs': []}, 'nextCursorMark': 'next'}]
        with patch('dq.solr.get_json', side_effect=responses) as get:
            self.assertEqual(list(missing_id_pages('url', 'vector')), [['a']])
            for call in get.call_args_list[2:]:
                self.assertEqual(call[1]['fq'], '{!frange l=0 u=0}exists($dq_field)')
