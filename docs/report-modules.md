# Internal processor modules

Rule implementations live in packages under `src/dq/processors/`. Processor packages contain lightweight metadata and checks/CSV handlers.
Markdown presentation lives separately under `src/dq/reports/`:

```text
src/dq/
  main.py                   action dispatch
  arguments.py              command-line syntax and help
  settings.py               field filters and option provenance
  listing.py                field-list output
  actions.py                execution, progress, errors, and output paths
  stored.py                 shared stored-value paging
  processors/
    registry.py             discovery and lazy handler loading
    missing_fields/         missing-document CSV
    empty_strings/          zero-length-string CSV
    whitespace_only/        whitespace-only-string CSV
    standard_text/          shared text checks and CSV findings
    date_checker/           deferred date implementation; no MVP handlers
    regex/                  regex loading and evaluation
      presets/              canned .regex files
  reports/
    date_checker.py         deferred date report; not available in MVP
    markdown.py             shared Markdown formatting
    checkup.py              special checkup summaries and field details
    links.py                source-query hyperlinks
```

## Adding a report

Create `src/dq/processors/my_report/` with an `__init__.py` containing:

```python
NAME = 'my_report'  # Must match the package directory; lowercase letters/digits/underscores.
DESCRIPTION = 'describe what this report checks'
REPORT = 'dq.reports.my_report:write_report'
RULE_TYPE = 'base'  # Required with CSV: base or composite.
CSV = 'dq.processors.my_report.csv_export:prepare_csv'  # Omit, or use None, if unsupported.
```

Discovery scans only packages inside `dq.processors`; it does not load scripts from
the working directory or configuration files. Metadata is imported to build help
and argument choices. A CSV rule declares `RULE_TYPE = 'base'` for one named
check or `RULE_TYPE = 'composite'` for a predefined combination. Supplying
multiple names to `--rules` forms a composite dynamically without changing its
component rules. Keep metadata free of server requests and implementation imports.
The selected handler module is imported only when its action runs. Handler paths
must stay inside their processor package, or for a report handler, the matching
`dq.reports.my_report` module. These are trusted internal modules,
not a sandbox for third-party code. Setuptools discovers and packages these
subpackages automatically.

Implement the report function with this interface:

```python
def write_report(target, output_path, *, include=(), exclude=(),
                 configuration_path=None, configuration_explicit=False,
                 option_details=(), connection=None, row_limit=-1, scan_progress=None, skip_null_values=False):
    # Query through the shared connection and write the Markdown output.
    pass
```

The runner resolves configuration and filters, supplies provenance and connection
settings, and supplies a base path in the configured reports directory
(default: `reports/`). Use `dq.files.field_output_paths` to plan per-field names
before scanning, then return the list of Markdown files actually written so
the final output summary includes them. Quick checkup returns only its overview;
full checkup also returns field details and CSVs. If the supplied base path is
returned, the runner treats it as the main report and groups the remaining files
under Other Created Files. Otherwise the Markdown files are the main reports;
images and other attachments appear under Other Created Files. Special reports provide their own analysis and layout. Ordinary rules expose
CSV only; do not register a generic Markdown renderer. Use
`dq.files.write_text` for atomic output and `dq.reports.markdown` for padded pipe
tables. Report handlers raise `ReportError` or the backend's error on failure.
When multiple reports are selected, all handlers are checked before execution;
each distinct report runs once in command-line order. Runtime failure in a later
report does not remove earlier completed reports.

For CSV support, validate the field selection and return `CsvExport`:

```python
from dq import stored
from dq.findings import CsvExport, Finding


def prepare_csv(target, *, include=(), exclude=(), connection=None,
                row_limit=-1, scan_progress=None, skip_null_values=False):
    selected = stored.fields(target, include, exclude, connection)

    def findings():
        for identifier, field, value in stored.values(
                target, selected, connection, row_limit=row_limit,
                scan_progress=scan_progress):
            if value == 'invalid':
                yield Finding(field, (identifier, 'my_report: invalid value', value))

    return CsvExport(selected, ['id', 'reason', 'value'], stored.pages(findings()))
```

`CsvExport` exposes selected field names before scanning and still supports
`header, pages` unpacking. A `Finding` is a normal row tuple with the original
field name attached as metadata, never as an extra CSV column. Attach it when
emitting findings for multiple fields; do not infer a field from reason text.

Pages lazily yield bounded lists of findings. Do not collect the entire result
set or print CSV yourself. The runner writes one UTF-8 `<FIELD_NAME>_<RULE_NAME>.csv`
per field with standard CSV quoting and CRLF line endings. It groups each page
by field and opens one destination at a time, bounding both memory and open files.
A zero-finding field still gets a header-only CSV. Reports use the same naming
with `.md`; checkup overviews link to the individual reports.

Filename field components retain ASCII letters, digits, dashes, and underscores;
each other character becomes one underscore. `field_output_paths` rejects names
that would collide, including case-only differences, before any file is replaced.
Missing directories are created and announced. Later runs replace the same files.
CSV runs end with Files created; report runs separate Main Report File(s)
from Other Created Files. All paths are relative to cwd.

Progress dots count source documents, not finding rows, and go to stdout.
Configuration details, export completion, and partial-export errors go to stderr.
Validate field selection before returning the lazy export so invalid selection
produces no CSV output.

Forward `scan_progress` unchanged to `dq.stored.values` (through any intermediate
findings function). The shared scanner announces its actual field selection,
counts each document once after its values are processed, and flushes progress
dots at the configured interval. Do not emit dots per finding or per value.

Pass `row_limit` to `dq.stored.values` to cap source documents across pages;
`-1` means no limit and `0` skips the scan. Do not cap finding rows instead:
all failing values from each selected document must be retained, with only
the first failure for each value. Scope descriptions
in reports must distinguish limited scans from collection-wide presence counts.

Use the supplied connection for all requests to preserve certificate and
authentication handling. The `missing_fields` module uses the existing Solr cursor
pager and returns `id,reason,value`, regardless of the actual unique-key
field name. It preserves unique-key discovery and partial-result checks.

New modules appear in CLI choices and generated report help without edits to
`main.py` or the registry. A module may expose only REPORT or only CSV. Planned
reports remain listed in the registry until implemented. Update the README,
INI template's action notes, and tests when adding user-visible capabilities.
Keep implementations compatible with Python 3.4.10 and use the standard library.

## Stored-value MVP processors

`standard_text` exposes a CSV rule. Date analysis and graphs are deferred beyond
the MVP; retained date modules have no registered handlers and are not called by
checkup. Native date fields receive presence checks only. Shared scanning
lives in `dq.stored`; findings CSV uses `id,reason,value` with a processor prefix
in the reason.

The `regex` package contains a shared engine, definition loader, and packaged
`presets/*.ini` settings and `presets/*.regex` patterns. These INI-defined processors are registered by name
alongside Python report packages. The conventional `processors/` directory beside
the loaded DQ INI file discovers user INI files with a `[processor]` section;
when no DQ INI is loaded, that directory is relative to cwd. Other INI files are
ignored. Each rule references a raw `.regex` file with a path
relative to its INI file;
duplicate names are rejected. See the README for rule syntax, result selection,
and case/verbose/multiline flags. Configuration paths appear in report provenance.

A `must_match` rule may reference multiple regex files, one per INI continuation
line. They are alternatives (OR), evaluated as one named rule. A failure means
none matched; successful-result mode emits one row when any matches.

`skip_null_values` is a shared action setting. Pass it to the shared
`standard_text.value_reasons` when using text checks; it omits only None/null
findings. Empty strings and whitespace still fail. Regex rules must never run on
null/blank values or emit them in succeeded output. Explicit missing_fields
presence checks retain their usual behavior.


### Special Reports and Supporting Files

The CLI distinguishes --rule NAME --action csv from --report NAME, which implies
the report action. Ordinary rules do not register generic Markdown output.
Special reports can orchestrate rules and produce several artifacts.

Quick checkup writes one summary table with collection-wide document counts
for each field, without CSVs. Full checkup uses one shared scan for counters,
bounded examples and per-field CSV findings. Its on_finding
callback sends full IDs and values to FieldCsvFiles with a 1,000-row buffer;
flush the final batch before publishing reports. Presence-only fields have no CSV.
Return every generated Markdown and CSV path so the final output lists supporting
files separately from the main report. Workload estimates cover the full selected
field set and follow Run Additional Checks.

Quick checkup appends field-specific commands based on planned rules. Preserve
the target/configuration, clear saved exclusions, quote shell arguments, escape
glob metacharacters in exact field names, and never put credentials in commands.

Built-in CSV handlers emit at most one row per field value, reporting the first
failed check in execution order. Full-checkup summaries use the same first-failure
logic. Multivalued fields retain each failing value. ScanProgress collects timing
measurements in memory; the action runner appends them to processing-stats.jsonl
only after successful output. Each timing includes the field-name list and an
explicit field count. It records count units so missing-document rates are
distinguishable from whole-document scan rates.
