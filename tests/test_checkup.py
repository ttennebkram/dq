"""Automatic check selection, overrides, and linked report output."""
import os
import tempfile
import unittest
from unittest.mock import patch
from dq.config import write_config
from dq.processors import ReportError
from dq.processors._checkup.processor import plan, overrides
from dq.reports.checkup import write_report


class CheckupTests(unittest.TestCase):
    def test_names_types_and_no_substring_matches(self):
        for name, expected in [('phone_s','us_phone'), ('primaryEmail_s','email'), ('social_security_s','ssn')]:
            self.assertIn(expected, plan({'name':name}, []))
        self.assertNotIn('us_phone', plan({'name':'microphone_s'}, []))
        self.assertEqual(list(plan({'name':'created','type':'pdate'}, [])), ['missing_fields'])
        self.assertNotIn('date_checker', plan({'name':'event_date_t','type':'text_general'}, []))
        self.assertNotIn('date_checker', plan({'name':'event_date_t','type':'text_general'}, [('*',['date_checker'])]))
        self.assertEqual(plan({'name':'phone_s'}, [('phone_*',[])]), {})
        self.assertEqual(set(plan({'name':'code_s'}, [('code_*',['email'])])), {'email', 'standard_text'})
        with self.assertRaises(ReportError):
            plan({'name':'phone_s'}, [('*',[]),('phone_*',[])])

    def test_standard_text_requires_text_schema_even_with_override(self):
        for type_class in ('TextField', 'StrField', 'SortableTextField'):
            self.assertIn('standard_text', plan({'name': 'custom', 'typeClass': 'solr.' + type_class}, []))
        for type_class in ('IntPointField', 'BoolField', 'DatePointField', 'DenseVectorField'):
            field = {'name': 'text_named_field', 'typeClass': 'solr.' + type_class}
            self.assertNotIn('standard_text', plan(field, []))
            self.assertNotIn('standard_text', plan(field, [('*', ['missing_fields', 'standard_text'])]))

    def test_string_unique_key_not_automatically_checked(self):
        field = {'name': 'custom_key_s', 'typeClass': 'solr.StrField', 'uniqueKey': True}
        self.assertNotIn('standard_text', plan(field, []))
        self.assertIn('standard_text', plan(field, [('*', ['standard_text'])]))

    def test_vectors_only_check_presence_even_with_overrides(self):
        field = {'name': 'email_date', 'type': 'custom_embedding',
                 'typeClass': 'solr.DenseVectorField'}
        self.assertEqual(set(plan(field, [])), {'missing_fields'})
        self.assertEqual(set(plan(field, [('*', ['missing_fields', 'email'])])), {'missing_fields'})
        self.assertEqual(plan(field, [('*', [])]), {})

    def test_overrides_survive_write_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'dq.ini')
            with open(path,'w') as stream:
                stream.write('[DEFAULT]\nmain_url = http://solr/c\n[checkup]\nPhone_* = missing_fields, us_phone\nother = none\n')
            write_config(path,'http://solr/c',None)
            self.assertEqual(overrides(path), [('Phone_*',['missing_fields','us_phone']),('other',[])])

    def test_one_scan_filtered_fields_and_links(self):
        fields=[{'name':'email_s','stored':True}, {'name':'created_dt','stored':True,'type':'pdate'},
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
                self.assertIn('did not match',detail)
                self.assertIn('- Finding rows: 4',detail)
                self.assertIn('standard_text: empty_values: empty string',detail)
                self.assertIn('standard_text: empty_values: whitespace only',detail)

    def test_empty_only_does_not_scan_values(self):
        with tempfile.TemporaryDirectory() as directory:
            config=os.path.join(directory,'dq.ini')
            with open(config,'w') as stream:stream.write('[checkup]\n* = missing_fields\n')
            with patch('dq.reports.checkup.list_fields',return_value=[{'name':'f','stored':True}]), \
                 patch('dq.reports.checkup.collection_document_count',return_value=0), \
                 patch('dq.reports.checkup.field_document_count',return_value=0), \
                 patch('dq.stored.values') as scan:
                write_report('url',os.path.join(directory,'full_checkup.md'),configuration_path=config)
            self.assertFalse(scan.called)
