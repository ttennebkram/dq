"""Report progress is visible, throttled, and independent of CSV diagnostics."""
import io
import re
import unittest
from unittest.mock import patch
from dq.progress import Progress
from dq.reports._checkup.processor import scan


class ProgressTests(unittest.TestCase):
    def test_stdout_throttle_and_forced_phases(self):
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.stdout', out), patch('sys.stderr', err), \
             patch('dq.progress.time.monotonic', side_effect=[0, 0, 1, 5, 6]):
            progress = Progress('checkup')
            progress.update('loading')
            progress.update('suppressed')
            progress.update('field email; test email')
            progress.update('complete', force=True)
        self.assertIn('loading', out.getvalue())
        self.assertNotIn('suppressed', out.getvalue())
        self.assertIn('field email; test email', out.getvalue())
        self.assertIn('complete', out.getvalue())
        self.assertEqual(err.getvalue(), '')

    def test_scan_reports_field_test_and_page_counts(self):
        out = io.StringIO()
        def source(target, fields, connection, progress, include_null=False, row_limit=-1, scan_progress=None):
            progress('fetching', 0)
            yield 'private-id', 'email_s', 'private-value'
            progress('scanned', 1)
        with patch('sys.stdout', out), patch('dq.stored.values', side_effect=source):
            scan('url', [{'name': 'email_s'}], {'email_s': {'email_composite': 'inferred'}},
                 progress=Progress('checkup', interval=0), total=1)
        text = out.getvalue()
        self.assertIn('fetching next Solr page', text)
        self.assertIn('field email_s; test email', text)
        self.assertIn('1 / 1 documents scanned', text)
        self.assertIn('scan complete: 1 documents; 1 stored values', text)
        self.assertNotIn('private-id', text)
        self.assertNotIn('private-value', text)


class FlushingStream(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushed = []

    def flush(self):
        self.flushed.append(self.getvalue())


def dot_count(text):
    # Timing and rates contain decimal points; only count the progress dots.
    return sum(len(re.match(r'\.*', line).group()) for line in text.splitlines())


class ScanProgressTests(unittest.TestCase):
    def test_total_formats_elapsed_time_and_rate_from_unrounded_duration(self):
        from dq.progress import ScanProgress
        cases = [(2000000, 125.0, 'Documents checked: 2,000,000 in 125.00 seconds (16,000.0 records/second)'),
                 (2000000, 1234.56, 'Documents checked: 2,000,000 in 1,234.56 seconds (1,620.0 records/second)'),
                 (1000, 2.345, 'Documents checked: 1,000 in 2.35 seconds (426.4 records/second)'),
                 (3, 10.0, 'Documents checked: 3 in 10.00 seconds (0.3 records/second)'),
                 (10, 0.001, 'Documents checked: 10 in < 0.01 seconds (10,000.0 records/second)'),
                 (0, 2.0, 'Documents checked: 0 in 2.00 seconds (0.0 records/second)')]
        for count, elapsed, expected in cases:
            with self.subTest(count=count, elapsed=elapsed):
                out = FlushingStream()
                progress = ScanProgress('email', every=0, stream=out)
                with patch('dq.progress.time.monotonic', side_effect=[0, elapsed]):
                    progress.start(['email_t'])
                    progress.finish(count)
                self.assertEqual(out.getvalue().splitlines()[-1], expected)
                self.assertEqual(out.flushed[-1], out.getvalue())

    def test_no_measurable_duration_does_not_divide_by_zero(self):
        from dq.progress import ScanProgress
        out = FlushingStream()
        with patch('dq.progress.time.monotonic', return_value=100):
            progress = ScanProgress('email', stream=out)
            progress.start(['email_t'])
            progress.finish(1)
        self.assertIn('< 0.01 seconds (records/second unavailable)', out.getvalue())

    def test_each_scan_starts_its_own_timer_and_keeps_its_unit(self):
        from dq.progress import ScanProgress
        out = FlushingStream()
        progress = ScanProgress('missing_fields_base', stream=out)
        with patch('dq.progress.time.monotonic', side_effect=[100, 102, 200, 204]) as clock:
            for _ in range(2):
                progress.start(['embedding'], unit='missing documents')
                progress.finish(20)
            progress.finish(20)
        self.assertIn('Missing documents checked: 20 in 2.00 seconds (10.0 records/second)', out.getvalue())
        self.assertIn('Missing documents checked: 20 in 4.00 seconds (5.0 records/second)', out.getvalue())
        self.assertEqual(clock.call_count, 4)

    def test_each_dot_is_visible_and_flushed_at_its_boundary(self):
        from dq.progress import ScanProgress
        out = FlushingStream()
        progress = ScanProgress('email', stream=out)
        progress.start(['email_t'])
        progress.update(999)
        self.assertFalse(out.getvalue().endswith('.'))
        progress.update(1000)
        self.assertTrue(out.getvalue().endswith('.'))
        self.assertEqual(out.flushed[-1], out.getvalue())
        progress.update(1999)
        self.assertEqual(dot_count(out.getvalue()), 1)
        progress.update(2000)
        self.assertTrue(out.getvalue().endswith('..'))
        self.assertEqual(out.flushed[-1], out.getvalue())
        progress.finish(2000)
        self.assertIn('email_t', out.getvalue())
        self.assertIn('Documents checked: 2,000 in ', out.getvalue())
        self.assertTrue(out.getvalue().endswith('records/second)\n'))

    def test_dots_can_be_disabled_and_do_not_require_a_terminal(self):
        from dq.progress import ScanProgress
        out = FlushingStream()
        self.assertFalse(out.isatty())
        progress = ScanProgress('email', every=0, stream=out)
        progress.start(['email_t'])
        progress.update(2000)
        progress.finish(2000)
        self.assertEqual(dot_count(out.getvalue()), 0)
        self.assertIn('email_t', out.getvalue())
        self.assertIn('Documents checked: 2,000', out.getvalue())

    def test_shared_scan_counts_documents_across_pages_not_values(self):
        from dq import stored
        from dq.progress import ScanProgress
        out = FlushingStream()
        fields = [{'name': 'email_t'}, {'name': 'notes_t'}]
        docs = [{'dq_key': str(i), 'dq_value0': ['private-value', 'private-value']} for i in range(5)]
        responses = [{'uniqueKey': 'id'},
                     {'response': {'docs': docs[:3]}, 'nextCursorMark': 'one'},
                     {'response': {'docs': docs[3:]}, 'nextCursorMark': 'two'}]
        def get(*args, **kwargs):
            self.assertIn('Field: email_t; rules: text', out.getvalue())
            self.assertIn('Field: notes_t; rules: text', out.getvalue())
            return responses.pop(0)
        with patch('dq.stored.get_json', side_effect=get) as fetch:
            values = list(stored.values('url', fields, page_size=3, include_null=True,
                                       row_limit=5, scan_progress=ScanProgress('text', 2, out)))
        self.assertEqual(len(values), 15)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(dot_count(out.getvalue()), 2)
        self.assertIn('Documents checked: 5 across 2 fields', out.getvalue())
        self.assertNotIn('private-value', out.getvalue())
        self.assertEqual([call[1]['rows'] for call in fetch.call_args_list[1:]], [3, 2])

    def test_failed_scan_keeps_actual_count_and_ends_the_progress_line(self):
        from dq import stored
        from dq.progress import ScanProgress
        from dq.solr import SolrError
        out = FlushingStream()
        responses = [{'uniqueKey': 'id'},
                     {'response': {'docs': [{'dq_key': 'private-id', 'dq_value0': 'private-value'}]},
                      'nextCursorMark': 'one'}, SolrError('unavailable')]
        with patch('dq.stored.get_json', side_effect=responses), self.assertRaises(SolrError):
            list(stored.values('url', [{'name': 'email_t'}], page_size=1,
                               scan_progress=ScanProgress('email', 1, out)))
        self.assertEqual(dot_count(out.getvalue()), 1)
        self.assertIn('Documents checked: 1 in ', out.getvalue())
        self.assertTrue(out.getvalue().endswith('records/second)\n'))
        self.assertNotIn('complete', out.getvalue())
        self.assertNotIn('private-id', out.getvalue())

    def test_csv_with_no_findings_still_shows_source_progress(self):
        import csv
        import os
        import tempfile
        from dq.config import DqConfig
        from dq.main import main
        out, err = FlushingStream(), io.StringIO()
        docs = [{'dq_key': str(i), 'dq_value0': 'person@example.com'} for i in range(5)]
        responses = [{'uniqueKey': 'id'}, {'response': {'docs': docs}, 'nextCursorMark': 'one'}]
        with tempfile.TemporaryDirectory() as directory:
            config = DqConfig(main_url='http://solr/c', reports_dir=directory, progress_every=4)
            with patch('dq.actions.load_config', return_value=config), \
                    patch('dq.stored.fields', return_value=[{'name': 'email_t', 'type': 'text_general'}]), \
                    patch('dq.stored.get_json', side_effect=responses), \
                    patch('sys.stdout', out), patch('sys.stderr', err):
                self.assertEqual(main(['--rule', 'email_composite', '--action', 'csv', '--rows', '5', '--progress_every', '2']), 0)
            with open(os.path.join(directory, 'email_t_email_composite.csv'), newline='') as stream:
                self.assertEqual(list(csv.reader(stream)), [['id', 'reason', 'value']])
        self.assertEqual(dot_count(out.getvalue()), 2)
        self.assertIn('Field: email_t; rules: email_composite', out.getvalue())
        self.assertIn('Documents checked: 5', out.getvalue())
        self.assertNotIn('person@example.com', out.getvalue())
        self.assertIn('Offending records exported: 0', err.getvalue())

    def test_full_checkup_shares_scan_and_does_not_interrupt_dots(self):
        from dq.progress import ScanProgress
        fields = [{'name': 'email_t'}, {'name': 'notes_t'}]
        plans = {'email_t': {'email_composite': ''}, 'notes_t': {'standard_text_composite': ''}}
        docs = [{'dq_key': str(i), 'dq_value0': 'person@example.com', 'dq_value1': 'notes'} for i in range(3)]
        responses = [{'uniqueKey': 'id'}, {'response': {'docs': docs}, 'nextCursorMark': 'one'}]
        out = FlushingStream()
        with patch('sys.stdout', out), patch('dq.stored.get_json', side_effect=responses) as fetch:
            scan('url', fields, plans, progress=Progress('full_checkup', interval=0),
                 row_limit=3, scan_progress=ScanProgress('full_checkup', 1, out))
        self.assertEqual(fetch.call_count, 2)
        self.assertNotIn('Field:', out.getvalue())
        self.assertIn('Progress: one dot per 1 records, shared across all listed fields', out.getvalue())
        self.assertIn('... Documents checked: 3 across 2 fields in ', out.getvalue())
        self.assertIn('stored-value scan complete: 3 documents; 6 stored values', out.getvalue())
        self.assertNotIn('fetching next Solr page', out.getvalue())

    def test_unlimited_missing_fields_base_uses_record_progress(self):
        from dq.progress import ScanProgress
        from dq.registry import load_handler
        out = FlushingStream()
        field = {'name': 'embedding', 'stored': True, 'typeClass': 'solr.DenseVectorField'}
        responses = [
            {'uniqueKey': 'id'},
            {'response': {'docs': [
                {'dq_key': 'a', 'dq_value0': False},
                {'dq_key': 'b', 'dq_value0': False},
            ]}, 'nextCursorMark': 'one'},
            {'response': {'docs': []}, 'nextCursorMark': 'one'},
        ]
        with patch('dq.rules.chain.stored.fields', return_value=[field]), \
                patch('dq.stored.get_json', side_effect=responses), \
                patch('sys.stderr', io.StringIO()):
            prepare_csv = load_handler('missing_fields_base', 'csv')
            header, pages = prepare_csv('url', scan_progress=ScanProgress('missing_fields_base', 1, out))
            self.assertEqual(sum(len(page) for page in pages), 2)
        self.assertIn('Field: embedding; rules: missing_fields_base', out.getvalue())
        self.assertIn('Documents checked: 2', out.getvalue())
        self.assertEqual(dot_count(out.getvalue()), 2)


class ProgressConfigurationTests(unittest.TestCase):
    def test_default_aliases_validation_and_ini_precedence(self):
        import os
        import tempfile
        from dq.arguments import build_parser
        from dq.config import DqConfig, ConfigError, load_config
        from dq.settings import resolve_progress_every
        parser = build_parser()
        self.assertEqual(resolve_progress_every(parser.parse_args([]), DqConfig()), 1000)
        for flag in ('--progress_every', '--progress-every'):
            self.assertEqual(resolve_progress_every(parser.parse_args([flag, '5_000']),
                                                    DqConfig(progress_every=200)), 5000)
            self.assertEqual(parser.parse_args([flag, '0']).progress_every, 0)
            for value in ('-1', '1.5', '1__000'):
                with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
                    parser.parse_args([flag, value])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            with open(path, 'w') as stream:
                stream.write('[DEFAULT]\nprogress_every=1_000\n[dq]\nprogress_every=20\n')
            self.assertEqual(load_config(path).progress_every, 20)
            self.assertEqual(load_config(start=directory).progress_every, 20)
            with open(path, 'w') as stream:
                stream.write('[DEFAULT]\nprogress_every=-1\n')
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_write_config_and_wizard_preserve_interval_without_a_prompt(self):
        import os
        import tempfile
        from dq.config import load_config, write_config
        from dq.main import main
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'dq.ini')
            write_config(path, 'http://solr/c', None, progress_every=50)
            with patch('sys.stdout', io.StringIO()), patch('builtins.input', side_effect=[''] * 3) as prompts:
                self.assertEqual(main(['--config_wizard', '--config', path]), 0)
            self.assertEqual(load_config(path).progress_every, 50)
            self.assertFalse(any('progress' in call[0][0] for call in prompts.call_args_list))
            with patch('sys.stdout', io.StringIO()):
                self.assertEqual(main(['--write_config', '--config', path, '--progress_every', '2_000']), 0)
            self.assertEqual(load_config(path).progress_every, 2000)
            with open(path) as stream:
                self.assertIn('# Previous progress_every = 50', stream.read())
