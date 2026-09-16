"""Automatic check selection and linked report output."""
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.errors import ReportError
from dq.reports._checkup.processor import plan
from dq.reports.checkup import write_report


class CheckupTests(unittest.TestCase):
    def test_names_types_and_no_substring_matches(self):
        for name, expected in [('phone_s','us_phone_composite'), ('primaryEmail_s','email_composite'), ('social_security_s','ssn_composite')]:
            self.assertIn(expected, plan({'name':name, 'typeClass':'solr.StrField'}))
        self.assertNotIn('us_phone_composite', plan({'name':'microphone_s', 'typeClass':'solr.StrField'}))
        self.assertNotIn('email_composite', plan({'name':'email_count', 'type':'pint'}))
        self.assertEqual(list(plan({'name':'created','type':'pdate'})), ['missing_fields_base'])
        self.assertNotIn('date_checker', plan({'name':'event_date_t','type':'text_general'}))

    def test_standard_text_composite_requires_text_schema(self):
        for type_class in ('TextField', 'StrField', 'SortableTextField'):
            self.assertIn('standard_text_composite', plan({'name': 'custom', 'typeClass': 'solr.' + type_class}))
        for type_class in ('IntPointField', 'BoolField', 'DatePointField', 'DenseVectorField'):
            field = {'name': 'text_named_field', 'typeClass': 'solr.' + type_class}
            self.assertNotIn('standard_text_composite', plan(field))

    def test_string_unique_key_not_automatically_checked(self):
        field = {'name': 'custom_key_s', 'typeClass': 'solr.StrField', 'uniqueKey': True}
        self.assertNotIn('standard_text_composite', plan(field))

    def test_vectors_only_check_presence(self):
        field = {'name': 'email_date', 'type': 'custom_embedding',
                 'typeClass': 'solr.DenseVectorField'}
        self.assertEqual(set(plan(field)), {'missing_fields_base'})

    def test_one_scan_filtered_fields_and_links(self):
        fields=[{'name':'email_s','stored':True,'typeClass':'solr.StrField'}, {'name':'created_dt','stored':True,'type':'pdate'},
                {'name':'phone_embedding','stored':True,'typeClass':'solr.DenseVectorField'}, {'name':'_hidden_','stored':True}, {'name':'unstored','stored':False}]
        source=[('empty','email_s',''),('blank','email_s',' \t'),('null','email_s',None),('1','email_s','bad'),('2','email_s','ok@example.com')]
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'full_checkup.md')
            with patch('dq.reports.checkup.list_fields',return_value=fields), \
                 patch('dq.reports.checkup.collection_document_count',return_value=3), \
                 patch('dq.reports.checkup.field_document_count',return_value=2), \
                 patch('dq.stored.values',return_value=iter(source)) as scan:
                write_report('http://solr/c',path)
            self.assertEqual(scan.call_count,1)
            self.assertEqual([f['name'] for f in scan.call_args[0][1]],['email_s'])
            with open(path) as stream: text=stream.read()
            self.assertIn('Report: `full_checkup`',text)
            self.assertIn('inferred from field-name',text)
            self.assertNotIn('_hidden_',text)
            self.assertNotIn('unstored',text)
            self.assertTrue(os.path.isfile(os.path.join(directory,'email_s_full_checkup.md')))
            self.assertFalse(any(name.endswith('.svg') for name in os.listdir(directory)))
            self.assertFalse(os.path.isfile(os.path.join(directory, 'created_dt_full_checkup.csv')))
            self.assertTrue(os.path.isfile(os.path.join(directory, 'email_s_full_checkup.csv')))
            self.assertNotIn('date_checker', text)
            with open(os.path.join(directory,'email_s_full_checkup.md')) as stream:
                detail = stream.read()
            self.assertIn('no configured regex matched',detail)
            self.assertIn('- Finding rows: 4',detail)
            self.assertIn('empty_strings_base: empty string',detail)
            self.assertIn('whitespace_only_base: whitespace-only string',detail)

    def test_empty_only_does_not_scan_values(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('dq.reports.checkup.list_fields',return_value=[{'name':'created_dt','stored':True,'type':'pdate'}]), \
                 patch('dq.reports.checkup.collection_document_count',return_value=0), \
                 patch('dq.reports.checkup.field_document_count',return_value=0), \
                 patch('dq.stored.values') as scan:
                write_report('url',os.path.join(directory,'full_checkup.md'))
            self.assertFalse(scan.called)
