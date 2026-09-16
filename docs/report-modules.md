# Internal Rules and Reports

DQ keeps stored-value rules and special reports in separate package trees:

```text
src/dq/
  registry.py                         rule/report discovery and lazy loading
  errors.py                           shared ReportError
  rules/
    code_points_base/                 Python base rule
    missing_fields_base/              Python base rule
    email_base/                       declarative regex base rule
    standard_text_composite/          predefined composite rule
    email_composite/                  predefined composite rule
    regex/                            shared regex loader and evaluator
    chain.py                          ordered base-rule evaluation
    composites.py                     composite discovery and flattening
  reports/
    quick_checkup/                    quick_checkup registration and handler
    full_checkup/                     full_checkup registration and handler
    _checkup/                         shared checkup planning and scanning
    markdown.py                       shared Markdown formatting
    links.py                          source-query hyperlinks
```

Every public rule package name ends in `_base` or `_composite`. Every special
report has its own package under `src/dq/reports/`. `dq.registry` discovers the
metadata packages while building catalogs and imports implementation modules only
when the selected rule or report runs.

## Adding a Python Base Rule

Create `src/dq/rules/my_rule_base/`. Its `__init__.py` contains only metadata:

```python
NAME = 'my_rule_base'
DESCRIPTION = 'describe the failed values'
RULE_TYPE = 'base'
CSV = 'dq.rules.my_rule_base.processor:prepare_csv'
```

The directory and `NAME` must match and end in `_base`. The handler returns a
`CsvExport`:

```python
from dq import stored
from dq.findings import CsvExport, Finding


def prepare_csv(target, *, include=(), exclude=(), connection=None,
                row_limit=-1, scan_progress=None, skip_null_values=False):
    selected = stored.fields(target, include, exclude, connection)

    def findings():
        values = stored.values(target, selected, connection,
                               row_limit=row_limit,
                               scan_progress=scan_progress)
        for identifier, field, value in values:
            if value == 'invalid':
                yield Finding(field, (identifier,
                                      'my_rule_base: invalid value', value))

    return CsvExport(selected, ['id', 'reason', 'value'],
                     stored.pages(findings()))
```

The runner writes one UTF-8 `<FIELD_NAME>_<RULE_NAME>.csv` file per selected
field. A `Finding` attaches the original field as metadata; it does not add a CSV
column. Stream pages instead of collecting an entire result set. Forward
`row_limit`, `scan_progress`, and the connection to shared scanners.

## Adding a Regex Base Rule

Create `src/dq/rules/my_format_base/` with:

- `__init__.py`
- `my_format_base.ini`
- one or more `.regex` files referenced by the INI file

The rule name comes from its directory, which must end in `_base`. Its settings
file is named `rule.ini`. Pattern paths are relative to the
INI file. The shared regex engine supplies the CSV handler.

During the MVP, add regex rule packages directly under `src/dq/rules/` and
include them in the source distribution. Loading project-specific definitions
from a separate `custom_rules/` directory is planned after the MVP.

## Adding a Predefined Composite Rule

Create `src/dq/rules/my_check_composite/__init__.py`:

```python
NAME = 'my_check_composite'
DESCRIPTION = 'standard checks followed by a format check'
RULE_TYPE = 'composite'
RULES = ('standard_text_composite', 'my_format_base')
```

Add the package module to `_MODULES` in `dq.rules.composites`. Composite rules may
contain other composites. DQ flattens them into one ordered, deduplicated base-rule
list and rejects cycles. Supplying multiple names with `--rules` creates the same
kind of chain dynamically. For each value, the first failed base rule is exported.

## Adding a Special Report

Create `src/dq/reports/my_report/`. Its `__init__.py` contains:

```python
NAME = 'my_report'
DESCRIPTION = 'describe the coordinated analysis'
REPORT = 'dq.reports.my_report.report:write_report'
```

Implement the handler in `report.py`:

```python
def write_report(target, output_path, *, include=(), exclude=(),
                 configuration_path=None, configuration_explicit=False,
                 option_details=(), connection=None, row_limit=-1,
                 scan_progress=None, skip_null_values=False):
    # Query through the shared connection and write the Markdown output.
    return [output_path]
```

Return every Markdown, CSV, and image path created by the report so the final
summary can separate the main report from supporting files. Use
`dq.files.write_text` for atomic text output, `dq.files.field_output_paths` for
safe per-field names, and `dq.reports.markdown` for Markdown tables.

Rules default to the CSV action. Reports imply the report action. A command cannot
combine `--rule` and `--report`. Keep metadata modules free of server requests and
implementation imports, keep all code compatible with Python 3.4.10, and update
the README, INI template, and tests for user-visible additions.
