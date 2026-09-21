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
        for name, expected in [('phone_s','us_phone_composite'),
                               ('primaryEmail_s','email_composite'),
                               ('social_security_s','ssn_composite'),
                               ('legacyPartNumber','part_number_example_composite')]:
            self.assertIn(expected, plan({'name':name, 'typeClass':'solr.StrField'}))
        self.assertNotIn('us_phone_composite', plan({'name':'microphone_s', 'typeClass':'solr.StrField'}))
        self.assertNotIn('us_phone_composite', plan({'name':'microphone_text', 'typeClass':'solr.StrField'}))
        self.assertNotIn('email_composite', plan({'name':'email_count', 'type':'pint'}))
        self.assertEqual(list(plan({'name':'created','type':'pdate'})), ['missing_fields_base'])
        self.assertNotIn('date_checker', plan({'name':'event_date_t','type':'text_general'}))

    def test_multiple_automatic_matches_choose_one_deterministically(self):
        checks = plan({'name': 'email_phone_t', 'typeClass': 'solr.StrField'})
        self.assertIn('email_composite', checks)
        self.assertNotIn('us_phone_composite', checks)
        self.assertEqual(checks.automatic_selected, 'email_composite')
        self.assertEqual(checks.automatic_matches,
                         (('email_composite', 'email'),
                          ('us_phone_composite', 'phone')))

        three_matches = plan({'name': 'email_part_number_t',
                              'typeClass': 'solr.StrField'})
        self.assertEqual(three_matches.automatic_selected, 'email_composite')
        self.assertEqual(three_matches.automatic_matches,
                         (('email_composite', 'email'),
                          ('part_number_example_composite', 'part + number')))

    def test_base_rule_can_advertise_automatic_matching(self):
        rules = {
            'account_code_base': {
                'automatic_field_types': ('text',),
                'automatic_field_name_patterns': (('account', 'code'),),
                'path': '/example/account_code_base/rule.ini',
            },
        }
        with patch('dq.reports._checkup.processor._automatic_rules',
                   return_value=rules):
            checks = plan({'name': 'legacyAccountCode',
                           'typeClass': 'solr.StrField'})
        self.assertEqual(list(checks),
                         ['missing_fields_base', 'account_code_base'])

    def test_quick_checkup_table_logs_multiple_matches_and_selection(self):
        field = {'name': 'email_phone_t', 'type': 'text_general',
                 'typeClass': 'solr.TextField', 'stored': True}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'quick_checkup.md')
            with patch('dq.reports.checkup.list_fields', return_value=[field]), \
                    patch('dq.reports.checkup.collection_document_count',
                          return_value=10), \
                    patch('dq.reports.checkup.field_document_count',
                          return_value=10):
                write_report('http://solr/c', path, mode='lite')
            with open(path) as stream:
                report = stream.read()
        self.assertIn('email_composite (selected; also matched '
                      'us_phone_composite (phone))', report)

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
        source=[('empty','email_s',''),('blank','email_s',' \t'),('null','email_s',None),('1','email_s','bad'),('2','email_s','ok@example.com'),
                ('date-null','created_dt',None), ('vector-null','phone_embedding',None)]
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'full_checkup.md')
            with patch('dq.reports.checkup.list_fields',return_value=fields), \
                 patch('dq.reports.checkup.collection_document_count',return_value=3), \
                 patch('dq.reports.checkup.field_document_count',return_value=2), \
                 patch('dq.stored.values',return_value=iter(source)) as scan:
                write_report('http://solr/c',path)
            self.assertEqual(scan.call_count,1)
            self.assertEqual([f['name'] for f in scan.call_args[0][1]],
                             ['email_s', 'created_dt', 'phone_embedding'])
            with open(path) as stream: text=stream.read()
            self.assertIn('Report: `full_checkup`',text)
            self.assertNotIn('## Check Selection', text)
            self.assertNotIn('_hidden_',text)
            self.assertNotIn('unstored',text)
            self.assertFalse(os.path.isfile(os.path.join(directory,'email_s_full_checkup.md')))
            self.assertFalse(any(name.endswith('.svg') for name in os.listdir(directory)))
            self.assertTrue(os.path.isfile(os.path.join(directory, 'created_dt_missing_fields_base.csv')))
            self.assertTrue(os.path.isfile(os.path.join(directory, 'phone_embedding_missing_fields_base.csv')))
            with open(os.path.join(directory, 'created_dt_missing_fields_base.csv')) as stream:
                self.assertIn('date-null,missing_fields_base: missing or null,', stream.read())
            with open(os.path.join(directory, 'phone_embedding_missing_fields_base.csv')) as stream:
                self.assertIn('vector-null,missing_fields_base: missing or null,', stream.read())
            self.assertTrue(os.path.isfile(os.path.join(directory, 'email_s_email_composite.csv')))
            self.assertNotIn('date_checker', text)
            with open(os.path.join(directory,'email_s_email_composite.csv')) as stream:
                findings = stream.read()
            self.assertIn('no configured regex matched', findings)
            self.assertIn('empty_strings_base: empty string', findings)
            self.assertIn('whitespace_only_base: whitespace-only string', findings)

    def test_empty_only_does_not_scan_values(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('dq.reports.checkup.list_fields',return_value=[{'name':'created_dt','stored':True,'type':'pdate'}]), \
                 patch('dq.reports.checkup.collection_document_count',return_value=0), \
                 patch('dq.reports.checkup.field_document_count',return_value=0), \
                 patch('dq.stored.values') as scan:
                write_report('url',os.path.join(directory,'full_checkup.md'))
            self.assertFalse(scan.called)
