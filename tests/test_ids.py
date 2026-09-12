"""Focused regression checks for bounded ID export and CLI output separation."""

import contextlib
import io
import os
import unittest
import sys
from unittest.mock import patch

from dq.cli import build_parser, main
from dq.config import DqConfig
from dq.solr import SolrError, missing_id_pages


@contextlib.contextmanager
def redirect_stdout(stream):
    old = sys.stdout
    sys.stdout = stream
    try:
        yield stream
    finally:
        sys.stdout = old


@contextlib.contextmanager
def redirect_stderr(stream):
    old = sys.stderr
    sys.stderr = stream
    try:
        yield stream
    finally:
        sys.stderr = old


def page(ids, cursor, **header):
    return {"responseHeader": header,
            "response": {"docs": [{"key_s": value} for value in ids]},
            "nextCursorMark": cursor}


class CursorTests(unittest.TestCase):
    def test_pages_are_lazy_and_use_discovered_key(self):
        responses = [{"uniqueKey": "key_s"}, page(["a", "b"], "one"),
                     page(["c"], "two"), page([], "two")]
        with patch("dq.solr.get_json", side_effect=responses) as get:
            pages = missing_id_pages("http://solr/c", "title_s", page_size=2)
            self.assertEqual(get.call_count, 0)
            self.assertEqual(next(pages), ["a", "b"])
            self.assertEqual(get.call_count, 2)
            self.assertEqual(list(pages), [["c"]])
            calls = get.call_args_list[1:]
            self.assertEqual([c[1]["cursorMark"] for c in calls], ["*", "one", "two"])
            for call in calls:
                self.assertEqual(call[1]["fl"], "key_s")
                self.assertEqual(call[1]["sort"], "key_s asc")
                self.assertEqual(call[1]["rows"], 2)
                self.assertEqual(call[1]["fq"], "{!frange l=0 u=0}exists($dq_field)")
                self.assertEqual(call[1]["dq_field"], "title_s")
                self.assertNotIn("start", call[1])

    def test_empty_results(self):
        with patch("dq.solr.get_json", side_effect=[{"uniqueKey": "key_s"}, page([], "*")]):
            self.assertEqual(list(missing_id_pages("url", "field")), [])

    def test_invalid_or_partial_pages_fail(self):
        for response in [page(["a"], "one", partialResults=True),
                         page([], "*", partialResults="omitted"),
                         {"response": {"docs": []}},
                         page([None], "one"), page(["a\nb"], "one"),
                         page(["a"], "*")]:
            with self.subTest(response=response), patch("dq.solr.get_json", side_effect=[{"uniqueKey": "key_s"}, response]):
                with self.assertRaises(SolrError):
                    list(missing_id_pages("url", "field"))

    def test_later_failure_preserves_streaming(self):
        with patch("dq.solr.get_json", side_effect=[{"uniqueKey": "key_s"}, page(["a"], "one"), SolrError("offline")]):
            pages = missing_id_pages("url", "field")
            self.assertEqual(next(pages), ["a"])
            with self.assertRaises(SolrError):
                next(pages)


class CliTests(unittest.TestCase):
    def test_repeated_report_lists_are_flattened(self):
        with patch("dq.cli.load_config", return_value=DqConfig()), \
             patch("dq.cli.collection_url", return_value="http://solr/c"), \
             patch("dq.cli.write_empty_fields_report") as write, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--report", "empty_fields", "empty_fields",
                                   "--reports", "empty_fields"]), 0)
        self.assertEqual(os.path.basename(write.call_args[0][1]), "empty_fields.md")
        details = write.call_args[1]["option_details"]
        self.assertEqual(details[0][1], "empty_fields, empty_fields, empty_fields")

    def test_alias(self):
        for flag in ("--ids", "-id"):
            self.assertEqual(build_parser().parse_args([flag, "empty_fields"]).ids, "empty_fields")

    def test_action_conflict_is_rejected_before_network(self):
        for other in (["--report", "empty_fields"], ["--list_fields"], ["--write_config"]):
            with self.subTest(other=other), patch("dq.cli.load_config") as load, \
                 redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(["--ids", "empty_fields"] + other)
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(load.called)

    def run_export(self, fields, pages):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("dq.cli.load_config", return_value=DqConfig()), \
             patch("dq.cli.collection_url", return_value="http://solr/c"), \
             patch("dq.cli.list_fields", return_value=fields), \
             patch("dq.cli.missing_id_pages", return_value=iter(pages)) as fetch, \
             redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                status = main(["--ids", "empty_fields"])
            except SystemExit as error:
                status = error.code
        return status, stdout.getvalue(), stderr.getvalue(), fetch

    def test_ids_only_on_stdout(self):
        status, out, err, _ = self.run_export([{"name": "title_s", "stored": True}], [["a", "b"], ["c"]])
        self.assertEqual(status, 0)
        self.assertEqual(out, "a\nb\nc\n")
        self.assertIn("3 IDs exported", err)

    def test_ambiguous_empty_or_nonstored_selection(self):
        for fields in [[], [{"name": "a"}, {"name": "b"}], [{"name": "a", "stored": False}]]:
            with self.subTest(fields=fields):
                status, out, err, fetch = self.run_export(fields, [])
                self.assertEqual(status, 2)
                self.assertEqual(out, "")
                self.assertIn("dq: error:", err)
                self.assertFalse(fetch.called)


if __name__ == "__main__":
    unittest.main()
