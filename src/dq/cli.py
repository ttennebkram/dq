"""Command-line entry point for DQ2."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dq import __version__
from dq.config import (
    ConfigError,
    DqConfig,
    collection_url,
    load_config,
    main_url_has_collection,
    write_config,
)
from dq.field_selection import select_fields
from dq.reports import ReportError, write_empty_fields_report
from dq.solr import SolrError, list_fields


REPORT_NAMES = ("empty_fields", "term_stats", "code_points", "date_checker")


def _yes_no(value: object) -> str:
    return "yes" if value is True else "no"


def _configured_value_source(
    *,
    command_line_value: object,
    environment_name: str,
    config: DqConfig,
    explicit_config: bool,
) -> str:
    if command_line_value is not None:
        return "command line"
    if explicit_config:
        return f"configuration file {config.source} specified by --config"
    if environment_name in os.environ:
        return f"environment variable {environment_name}"
    if config.source is not None:
        return f"default configuration file {config.source}"
    return "not set"


def _report_option_details(
    options: argparse.Namespace,
    config: DqConfig,
    target: str,
    output_path: Path,
) -> list[tuple[str, str, str]]:
    main_url = options.main_url or config.main_url or ""
    main_url_source = _configured_value_source(
        command_line_value=options.main_url,
        environment_name="DQ_MAIN_URL",
        config=config,
        explicit_config=bool(options.config),
    )
    if main_url_has_collection(main_url):
        path_parts = [
            unquote(part) for part in urlsplit(target).path.split("/") if part
        ]
        collection = path_parts[-1]
        collection_source = f"included in main_url from {main_url_source}"
    else:
        collection = options.collection or config.collection or ""
        collection_source = _configured_value_source(
            command_line_value=options.collection,
            environment_name="DQ_COLLECTION",
            config=config,
            explicit_config=bool(options.config),
        )

    if config.source is None:
        configuration_value = "none"
        configuration_source = "no configuration file read"
    elif options.config:
        configuration_value = str(config.source)
        configuration_source = "specified by --config"
    else:
        configuration_value = str(config.source)
        configuration_source = "default configuration lookup"

    include_value = ", ".join(options.include_fields) or "all fields"
    include_source = "command line" if options.include_fields else "built-in default"
    if options.exclude_fields:
        exclude_value = ", ".join(options.exclude_fields)
        exclude_source = "command line"
    elif options.include_fields:
        exclude_value = "none"
        exclude_source = "built-in default with explicit field filters"
    else:
        exclude_value = "_*_"
        exclude_source = "built-in default"

    return [
        ("report", ", ".join(options.report), "command line --report/--reports"),
        ("main_url", main_url, main_url_source),
        ("collection/index", collection, collection_source),
        ("configuration file", configuration_value, configuration_source),
        ("include_fields", include_value, include_source),
        ("exclude_fields", exclude_value, exclude_source),
        ("output file", str(output_path), "built-in default"),
    ]


def print_fields(
    target: str,
    *,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    configuration_path: Path | None = None,
    configuration_explicit: bool = False,
) -> None:
    fields = select_fields(list_fields(target), include=include, exclude=exclude)
    columns = (
        ("FIELD", "name"),
        ("TYPE", "type"),
        ("STORED", "stored"),
        ("INDEXED", "indexed"),
        ("DOC VALUES", "docValues"),
        ("MULTI VALUED", "multiValued"),
        ("DOCUMENTS", "documents"),
        ("SCHEMA FIELD", "schemaField"),
    )
    rows = [
        [
            str(field.get(key, ""))
            if key in {"name", "type", "documents", "schemaField"}
            else _yes_no(field.get(key))
            for _, key in columns
        ]
        for field in fields
    ]
    widths = [
        max([len(heading), *(len(row[index]) for row in rows)])
        for index, (heading, _) in enumerate(columns)
    ]

    print(f"Solr collection: {target.rstrip('/')}")
    if configuration_path is not None:
        source = (
            "specified by --config" if configuration_explicit else "default configuration"
        )
        print(f"Configuration: {configuration_path} ({source})")
    print(f"Fields: {len(rows)}")
    print()
    print("  ".join(heading.ljust(widths[index]) for index, (heading, _) in enumerate(columns)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""\
DQ2 generates data-quality reports for Apache Solr, Elasticsearch,
and OpenSearch indexes.

Reports use Markdown so a run can produce multiple documents with links
between summary and detail pages. Stored fields are included by default;
include and exclude patterns will allow a run to focus on selected fields.""",
        epilog="""\
Saved target configuration:
  dq.ini in the current directory or a parent directory
  ~/.config/dq/config.ini as the user fallback

Reports:
  empty_fields   IMPLEMENTED - find fields that are not fully populated
  term_stats     PLANNED - analyze indexed terms and token lengths
  code_points    PLANNED - find tokens spanning unexpected Unicode classes
  date_checker   PLANNED - analyze stored date values and ranges

Planned utility and comparison commands:
  doc_count, diff_empty_fields, diff_ids, diff_schema, diff_config, dump_ids,
  delete_by_ids, solr_to_solr, solr_to_csv, hash_and_shard

Report example:
  dq --report empty_fields

Report selection:
  --report and --reports are equivalent; both accept one or more names

Field filtering examples (simple glob patterns, not regular expressions):
  --include_fields 'file_*' --include_fields 'content'
  --exclude_fields '*_vector' --exclude_fields '_*'

Project documentation:
  /Users/mbennett/Dropbox/dev/dq/README.md
""",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--report",
        "--reports",
        metavar="NAME",
        action="extend",
        nargs="+",
        choices=REPORT_NAMES,
        default=[],
        help="generate one or more named Markdown reports; repeatable",
    )
    parser.add_argument(
        "--list_fields",
        "--list-fields",
        action="store_true",
        help="list Solr collection fields and their schema properties",
    )
    parser.add_argument(
        "--include_fields",
        "--include_field",
        "--include-fields",
        "--include-field",
        metavar="PATTERN",
        action="append",
        default=[],
        help="include field names matching a simple glob, not a regex; repeatable",
    )
    parser.add_argument(
        "--exclude_fields",
        "--exclude_field",
        "--exclude-fields",
        "--exclude-field",
        metavar="PATTERN",
        action="append",
        default=[],
        help="exclude field names matching a simple glob, not a regex; repeatable",
    )
    parser.add_argument(
        "--main_url",
        "--main-url",
        metavar="URL",
        help="server base URL, optionally including the collection or index",
    )
    parser.add_argument(
        "--collection",
        "--index",
        metavar="NAME",
        help="collection or index name (--index is a synonym)",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="read existing FILE; with --write_config, create or update FILE",
    )
    parser.add_argument(
        "--write_config",
        "--write-config",
        action="store_true",
        help="write settings to ./dq.ini or the file named by --config",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = list(argv) if argv is not None else sys.argv[1:]
    options = parser.parse_args(arguments)
    action_count = sum(
        (bool(options.write_config), bool(options.list_fields), bool(options.report))
    )
    if action_count > 1:
        parser.error("choose only one action: --report, --list_fields, or --write_config")
    if options.write_config:
        try:
            output_path = (
                Path(options.config).expanduser().resolve()
                if options.config
                else Path.cwd() / "dq.ini"
            )
            config = (
                load_config(str(output_path))
                if output_path.is_file()
                else DqConfig()
            )
            resolved_main_url = options.main_url or config.main_url
            if not resolved_main_url:
                raise ConfigError(
                    "main_url is required; use --main_url, DQ_MAIN_URL, or an existing config"
                )
            if options.main_url and main_url_has_collection(options.main_url):
                resolved_collection = options.collection
            else:
                resolved_collection = options.collection or config.collection
            collection_url(
                DqConfig(main_url=resolved_main_url, collection=resolved_collection)
            )
            write_config(output_path, resolved_main_url, resolved_collection)
            print(f"Wrote configuration: {output_path}")
        except ConfigError as error:
            parser.exit(2, f"dq: error: {error}\n")
        return 0
    if options.list_fields:
        try:
            config = load_config(options.config)
            target = collection_url(
                config,
                main_url=options.main_url,
                collection=options.collection,
            )
            print_fields(
                target,
                include=options.include_fields,
                exclude=options.exclude_fields,
                configuration_path=config.source,
                configuration_explicit=bool(options.config),
            )
        except (ConfigError, SolrError) as error:
            parser.exit(2, f"dq: error: {error}\n")
        return 0
    if options.report:
        try:
            config = load_config(options.config)
            target = collection_url(
                config,
                main_url=options.main_url,
                collection=options.collection,
            )
            unimplemented = [name for name in options.report if name != "empty_fields"]
            if unimplemented:
                names = ", ".join(dict.fromkeys(unimplemented))
                raise ReportError(f"report not implemented yet: {names}")
            output_path = Path.cwd() / "empty_fields.md"
            write_empty_fields_report(
                target,
                output_path,
                include=options.include_fields,
                exclude=options.exclude_fields,
                configuration_path=config.source,
                configuration_explicit=bool(options.config),
                option_details=_report_option_details(
                    options, config, target, output_path
                ),
            )
            print(f"Wrote report: {output_path}")
        except (ConfigError, ReportError, SolrError) as error:
            parser.exit(2, f"dq: error: {error}\n")
        return 0
    if not arguments:
        parser.print_help(sys.stderr)
    try:
        config = load_config(options.config)
        target = collection_url(
            config,
            main_url=options.main_url,
            collection=options.collection,
        )
    except ConfigError as error:
        parser.exit(2, f"dq: error: {error}\n")
    if config.source is None:
        configuration_detail = ""
    elif options.config:
        configuration_detail = (
            f" using configuration file {config.source} specified by --config"
        )
    else:
        configuration_detail = f" using default configuration file {config.source}"
    parser.exit(
        2,
        f"dq: error: target resolves to {target}{configuration_detail}, "
        "but no action was selected; "
        "use --report NAME, --list_fields, or --write_config\n",
    )
