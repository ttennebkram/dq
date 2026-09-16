Configuration
-------------

### Configuration wizard

Run `bin/dq --config_wizard` or `bin/dq --setup_wizard` to walk through the
standard settings: `main_url`, collection/index, optional Basic authentication username
and password. Field filters are configured separately in the INI file or on the
command line; the wizard does not ask for them.
The Configuration Wizard header shows the full destination path and whether
the file will be created or updated. It defaults to `dq.ini` in the current
directory; cancel with Ctrl-C and use `--config FILE` to choose another file:

```sh
bin/dq --config_wizard
bin/dq --config_wizard --config targets.ini
```

The wizard uses command-line settings first, then existing values in the
destination file. It does not inherit environment variables or other discovered
config files. For a new file, the suggested URL is `http://localhost:8983/solr` and the
collection is `dq-demo`, matching the test-data loader. The URL prompt also
shows separate Elasticsearch and OpenSearch examples. Both use
`http://localhost:9200`, because both engines normally use HTTP port 9200.
The Solr suggestions apply only when no CLI or saved value is available.
Enter keeps a default; `-` clears an optional value. If the URL includes a
collection, the wizard explains that the separate collection setting is omitted.
The username defaults to blank when unset; no password is requested or saved
when the username is blank. Enter keeps a saved username; `-` clears it and
also clears the password. Password entry is hidden and the
summary redacts it, but the saved INI contains plaintext credentials.

Existing include/exclude filters are preserved; explicit CLI overrides are
accepted without prompting. New configurations leave
field filters unset, retaining the usual default exclusion of `_*_`.
The wizard does not prompt for certificates.
Normal HTTPS uses Python's default trust store; `trust_certificate` is only for
self-signed certificates or private CAs not already trusted. Advanced CLI/INI
certificate settings are preserved and validated locally. INI paths are relative
to that file; CLI paths are relative to cwd. The wizard validates settings without
contacting the server, shows a summary, and asks before writing. Answer no, press Ctrl-C,
or end input to cancel without writing. It uses the same atomic, owner-only
file writing as `--write_config` and comments out changed old target/filter values.
Choose this action separately from reports, CSV export, listing, or `--write_config`.

### Testing Elasticsearch and OpenSearch Side by Side

Most users run only one of these engines, so both general examples use their
normal address, `http://localhost:9200`. Developers testing DQ against both
engines on one machine must assign a different HTTP port to one of them.

For example, keep Elasticsearch on 9200 and add this to OpenSearch's
`config/opensearch.yml` before restarting OpenSearch:

```yaml
http.port: 9201
```

The two test targets are then:

```text
Elasticsearch: http://localhost:9200
OpenSearch:    http://localhost:9201
```

Use separate DQ configuration files when the engines use different credentials
or index names, or select the server on the command line with `--main_url`.


The project includes a template containing every currently supported setting:

    ~/dev/dq/dq.ini.template

Copy it when starting configuration for another project:

    cp ~/dev/dq/dq.ini.template dq.ini

The template lists all supported INI settings: `main_url`, `collection`,
`username`, `password`, `trust_certificate`, `include_fields`, `exclude_fields`,
`reports_dir`, `rows` (synonym: `size`), `progress_every`, and `skip_null_values`.
It also documents the command-line-only options in comments; actions, `--config`,
`--help`, and `--version` are not INI settings. Update the template, this README,
and CLI help together whenever options or defaults change.

Edit the copied ``dq.ini`` for that server and collection. The template remains
unchanged as a reference as more settings are added to DQ.

DQ separates the server's main URL from the collection or index name. The
project-level ``dq.ini`` contains:

    [DEFAULT]
    main_url = http://localhost:8983/solr
    collection = my-files

``main_url`` may instead contain the collection or index. In that form,
``collection`` can be omitted:

    [DEFAULT]
    main_url = http://localhost:8983/solr/my-files

DQ inspects the URL path before reporting that a collection is missing. These
forms therefore resolve to the same endpoint:

    main_url = http://localhost:8983/solr
    collection = my-files

    main_url = http://localhost:8983/solr/my-files

Declaring the collection in both places is an error, even if both names match.
This prevents DQ from silently ignoring ``--collection`` or accidentally
querying a different collection:

    bin/dq --main_url http://localhost:8983/solr/my-files \
       --collection my-files \
       --list_fields

The command above exits with an explanation. Remove either the collection from
``main_url`` or the separate ``--collection`` option.

This makes the normal command short:

    bin/dq --list_fields

Both values can be overridden on the command line:

    bin/dq --main_url http://localhost:8983/solr \
       --collection my-files \
       --list_fields

``--index`` is a synonym for ``--collection`` for Elasticsearch and OpenSearch
terminology:

    bin/dq --main_url http://localhost:8983/solr \
       --index my-files \
       --list_fields

Hyphenated ``--main-url`` is accepted as an alias for ``--main_url``.

Configuration file lookup
~~~~~~~~~~~~~~~~~~~~~~~~~

Unless ``--config`` is supplied, DQ looks for the nearest ``dq.ini`` in the
current directory and then each parent directory. This allows commands run in
subdirectories to use the project's configuration. A user-wide configuration
fallback may be considered after the MVP.

Use a specific configuration file with:

    bin/dq --config /path/to/another.ini --list_fields

Without ``--write_config`` or ``--config_wizard``, the file named by ``--config`` must already exist.
DQ reports an error instead of silently falling back to another ``dq.ini`` or
to environment settings.

When combined with ``--write_config``, ``--config FILE`` names the file to
create or update:

    bin/dq --main_url http://localhost:8983/solr \
       --collection my-files \
       --config /path/to/another.ini \
       --write_config

Write the currently effective target settings to ``dq.ini`` in the current
directory:

    bin/dq --main_url http://localhost:8983/solr \
       --collection my-files \
       --write_config

This produces:

    [DEFAULT]
    main_url = http://localhost:8983/solr
    collection = my-files

If ``main_url`` already contains the collection, the file omits the separate
``collection`` key:

    bin/dq --main_url http://localhost:8983/solr/my-files --write_config

``--write-config`` is accepted as an alias. The command validates the effective
settings and updates ``dq.ini`` in the current directory. When a setting changes
or is removed, DQ leaves its old value in the file as a comment. For example,
changing the collection produces:

    [DEFAULT]
    main_url = http://localhost:8983/solr
    # Previous collection = my-files
    collection = another-collection

Unchanged settings are written normally and do not accumulate duplicate
comments.

The optional ``[dq]`` section is also supported and overrides values from
``[DEFAULT]`` in the same file.

Environment variables
~~~~~~~~~~~~~~~~~~~~~

The corresponding environment variables are:

    DQ_MAIN_URL=http://localhost:8983/solr
    DQ_COLLECTION=my-files

Value precedence
~~~~~~~~~~~~~~~~

From highest to lowest precedence:

1. ``--main_url`` and ``--collection`` command-line values
2. File supplied with ``--config``
3. ``DQ_MAIN_URL`` and ``DQ_COLLECTION`` environment variables
4. Nearest project ``dq.ini``

Command-line ``--main_url`` or ``--collection`` values may override only one
part while taking the other part from the selected configuration source.

The first live report command is:

    bin/dq --report quick_checkup \
       --main_url http://localhost:8983/solr \
       --collection my-files

### Saved field filters

Store simple glob patterns in `dq.ini`, one per line, indenting additional lines:

```ini
[dq]
include_fields = file_*
    content_*
exclude_fields = *_vector
    embedding_*
```

Patterns are not regex. Do not quote INI patterns or separate them with commas;
spaces and commas within a pattern are literal. Saved filters apply to reports,
`--list_fields`, and `--rule NAME`. Each selected stored field gets a separate report or CSV file.

Command-line `--include_fields` replaces the saved include list; `--exclude_fields`
replaces the saved exclude list independently. Supply multiple patterns after
one option or repeat that option. Use `--include_fields ''` or `--exclude_fields ''` to clear the
corresponding saved list for a run. When both effective lists are empty, the
usual `_*_` exclusion applies; use `--include_fields '*'` to include all names.
There are no environment variables for field filters.

`--write_config` saves the effective filters and preserves previous changed
filter values as comments. The report summary displays the effective patterns,
and Options Used identifies whether they came from CLI, INI, or defaults.


[Back to Quickstart](../README.md#quickstart)

## Document Limit

`--rows N` and `--size N` are synonyms for the maximum documents to check
per scan, across all pages. Save `rows = -1` in the INI file for no limit (the
default), `rows = 0` to skip document scans, or a positive integer for a limit.
INI `size` is also accepted. Single underscores between digits are supported
in both CLI and INI values, including Python 3.4: `--rows 1_000`, `--size 1_000`,
and `rows = 1_000` all mean 1000. Leading, trailing, or repeated underscores are
rejected. Saved settings use plain integers.

CLI overrides INI; if both CLI spellings appear,
the last wins. Conflicting aliases in one INI section are an error. `[dq]`
overrides `[DEFAULT]` even when the sections use different spellings.

`--write_config` and the wizard save the canonical `rows` name, preserving the
current limit and commenting out changed previous values. The wizard accepts
CLI overrides without adding a prompt. Reports include the effective limit
and its source. No environment variable applies to this setting.

Documents are read in unique-key order, not randomly. Each selected field produces
at most one CSV record per failing value, showing its first failed check.
Single-valued fields produce at most one row per document; multivalued fields
can produce multiple rows for different values. Presence counts
remain collection-wide, including those in quick and full checkups and field
listing. The limit applies to stored-value findings; the quick
report uses it when estimating the full report's workload.

## Checkup Reports

`quick_checkup` writes one Markdown report containing field-presence counts,
suggested rules, focused follow-up commands, and an estimate of the full-checkup
workload. It does not fetch stored values or create CSV files. **Presence check
only** means a field receives document counts; **Disabled** means its checks were
turned off in the configuration.

`full_checkup` scans stored values once across all selected fields. It writes an
overview, a detail report for each field, and
`<FIELD_NAME>_full_checkup.csv` for fields with stored-value checks. Detail reports
retain up to 100 examples; CSV files retain all findings with complete IDs and
values. A field with no findings gets a header-only CSV. Presence-only fields do
not get CSV files. Keep these supporting files with the overview when sharing it.

Missing counts use separate Solr field-existence queries and remain
collection-wide when `--rows` limits the value scan. Multivalued fields are
expanded; counts represent finding rows rather than distinct documents. DQ
reports only the first failed base rule for each value. Concurrent index changes
can affect results because a checkup is not a snapshot.

The quick report's workload estimate covers all selected fields together. Actual
full-checkup time varies with field sizes, selected fields, server load, and
network speed. Use `--include_fields` to focus the scan and `--rows` / `--size`
to limit source documents during testing. Each timing line identifies its engine
and uses only a benchmark recorded for that engine. If DQ has no benchmark for
the current engine, the unavailable message names that engine instead of reusing
another engine's timing range.

## Scan Progress

`progress_every = 1000` prints one immediately flushed dot for every 1,000
source documents processed. CLI `--progress_every N` (alias `--progress-every`)
overrides the INI value; underscores such as `5_000` are supported. `0` disables
dots while retaining field announcements and the processed count, elapsed seconds,
and average records/second. Timing includes server waits and value checks; the
rate counts source documents, not findings or multivalued items. The scan total
is labeled `Documents checked`; CSV completion separately labels `Offending records exported` (data rows, excluding the header). Multi-field runs show a
count for each field and an overall total. One source document may
produce zero, one, or multiple CSV rows. No environment variable applies. The
wizard preserves this setting without a prompt, and
`--write_config` saves it, commenting out a changed previous value.

Progress goes to stdout for reports and CSV exports. Source documents are counted
even when they produce no findings; multivalued items do not inflate the count.
Multiple fields in a shared scan are announced together. This does not affect
page size or the document limit. Unlimited vector-null exports count returned
missing documents and identify that unit. Presence-only reports do not scan.
Each new `processing-stats.jsonl` record includes the engine so Solr measurements
remain distinct from Elasticsearch/OpenSearch measurements.

## Report directory

`reports_dir` defaults to `reports/` in the current working directory. Run DQ
from the project root for normal use. Set `reports_dir = reports` in the INI
file to anchor the destination to that file's directory. `--reports_dir DIR`
(alias `--reports-dir`) overrides it, with relative paths resolved from cwd.
Missing directories are created automatically, and DQ announces when it creates
them. `--write_config` saves the value; the wizard preserves it and accepts a CLI
override. This setting affects Markdown reports, CSV exports, and supporting files.
Rule exports use `<FIELD_NAME>_<RULE_NAME>.csv`. Special reports choose their own
Markdown layout; quick checkup writes one summary without CSVs, while full
checkup includes per-field CSV findings from its shared stored-value scan.
For example, `--rule email_composite --include_field email_t` writes `reports/email_t_email_composite.csv`.
Quick checkup writes one summary; full checkup links to field reports and CSVs.
Final report output separates Main Report File(s) from Other Created Files.
CSV runs use Files created. All paths are relative to the working directory.
Later runs replace files with the same name. Field listing still uses stdout.


### Null Findings

`skip_null_values = false` includes null/missing findings by default. Set it to
`true`, or pass `--skip_null_values`, to omit only null findings from
composite and base rule chains. Empty strings, whitespace,
and other checks remain. Explicit missing_fields_base and presence counts are unchanged.
`--skip_null_values false` overrides a saved true setting. The wizard preserves
this option without a prompt; --write_config saves it and comments out changed
old values. Reports record the effective setting and its source.


### Rules, Reports and Actions

Use --rule NAME [NAME ...] for CSV findings; csv is the default rule action. --rules is a synonym.
Rules run in order during one scan; every rule must pass and the first failure
is exported. --report NAME
selects special analysis and implies --action report, which may also be explicit.
Report and rule names are separate. These selections are CLI-only, not INI keys.
Use `--list_reports` or `--list_rules` to print the available names on stdout;
these commands require neither a target nor an INI setting.
