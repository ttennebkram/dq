# Generate a Test Collection

In this guide, **ES includes OpenSearch and the free/open-source and commercial
editions of Elasticsearch**, for the shared index-creation and Bulk APIs used
here. The ES generator and submission script work with both engines and do not
require paid features.

Vocabulary Note: Solr calls a named set of documents a **collection**; Elasticsearch and
OpenSearch call it an **index**. In this documentation, both terms refer
to the same concept: the target dataset.

The [generator](generate-test-data-solr.py) creates JSON; [submit-to-solr.py](submit-to-solr.py)
creates the Solr collection when needed and loads the records.
Also see the project’s [bin directory](../bin/) for [`dq`](../bin/dq).
For this workflow, first enter `generate-test-collection/` from the project root.

## Quickstart

Start in the DQ project’s main directory, then change into this directory as
shown below. Python 3.4.10 or newer must be on PATH; no extra packages are needed.
Solr must be running. The loader automatically finds `../dq.ini` for connection
settings (unless a nearer `dq.ini` exists).

```bash
cd generate-test-collection

# 1. Generate test data in the current directory.
./generate-test-data-solr.py --count 1000 --incorrect_percent 20

# 2. Check the generated data file.
ls -l documents-solr.json

# 3. Create dq-demo if needed, then load the generated records.
./submit-to-solr.py --submit

# 4. Check the collection.
../bin/dq --main_url http://localhost:8983/solr/dq-demo --report quick_checkup
```

Both scripts run directly; you do not need a `python` prefix or a wrapper.
The generator creates `documents-solr.json` (records) and `expected-results.json` (the answer
key). The loader reads `documents-solr.json`, uses the connection settings from
`../dq.ini`, and targets `dq-demo`. Open `reports/quick_checkup.md` to see the results.

For a clean reload that removes old demo records and rebuilds its schema/configset:

```bash
./submit-to-solr.py --recreate_collection
```

For usage, run `./generate-test-data-solr.py` without arguments or
`./submit-to-solr.py` without arguments. Both display usage without writing
files or contacting Solr. The submission script also shows the absolute path to
`documents-solr.json`, existence, line count followed by byte count, last-modified time in the local
timezone, and readability. Line counting reads the file in bounded chunks without
parsing the JSON. Submission requires either `--submit` or
`--recreate_collection`; the latter deletes and rebuilds the demo before loading.

## About the data

This fixture is generated test data, not a dataset of real people. Email addresses
use example.com and phone numbers use the fictional 212-555-0100–0199 range.
SSNs are **synthetic format examples**, not verified unassigned numbers; never
use them as identities. Names and addresses are fictional placeholders, not
verified deliverable addresses. Files are covered by this project's Apache 2.0 license.

Text data fields end in `_t` and are explicitly stored and indexed as
`text_general`: first_name, last_name, street_address, city, state, postal_code,
country, email, phone, ssn, and notes. `id` is the unique key.
`event_date_dt` is a native stored/indexed Solr `pdate`. Date-format validation
is outside the MVP. Its injected defects are missing values, nulls, and future
dates; Solr rejects malformed date strings.

## Generate

`--count` is required and has no default. Start with `--count 1000`.
Running without arguments still displays usage without generating files.

From `generate-test-collection/` (Python 3.4.10 or newer; no extra dependencies), run
`./generate-test-data-solr.py` without arguments to see detailed usage. No-argument
runs do not generate or overwrite files. To generate data:

```bash
./generate-test-data-solr.py --count 1000 --incorrect_percent 20 --seed 42
./generate-test-data-solr.py --count 1000 --incorrect_percent 10
```

### Random runs and repeatable seeds

**The default is random. Omit `--seed` for a fresh error distribution each run.**

**To reproduce a run, supply its seed and the same generation options.** The
chosen seed is printed and saved in `expected-results.json`, even when selected randomly.
For exact reproduction, also use the same generator and Python version.

```bash
./generate-test-data-solr.py --count 1000 --incorrect_percent 20
./generate-test-data-solr.py --count 1000 --incorrect_percent 20 --seed 42
```

`--seed 0` and `--seed -1` are ordinary repeatable seeds, not random-mode switches.
The seed changes which records receive errors; the requested error counts and
sequential IDs remain the same.

The single `--incorrect_percent` setting applies to every field; per-field
overrides are outside the MVP. Each field independently gets the requested percentage of deliberately bad
records, rounded to the nearest document. For a 100-document example, there are exactly 20
bad records per field out of 100. The bad cases cycle through missing, explicit
null, empty string, whitespace-only, and malformed values: four of each per text field
in that 100-document example. Native dates instead cycle through missing, null, and
future dates, while keeping the same total error percentage. Small requested counts may not include every category.
A fixed seed reproduces the selection. Errors can overlap across fields, so a
per-field percentage is not the percentage of documents containing any error.

Generated files default to the current working directory. `--data_files_dir data`
writes to `data/` under that directory; an absolute path is used as given.
`documents-solr.json` is the input. `expected-results.json` records actual counts and every
injected defect separately; it is not indexed. Malformed names/addresses use
obviously bad placeholders and a replacement character, not geographic or
identity validation. Passing a regex only establishes the configured syntax.

## Load or recreate the Solr collection

```bash
./submit-to-solr.py --submit
# Delete and rebuild the demo collection and its configset:
./submit-to-solr.py --recreate_collection
```

Run from this directory; the loader searches upward to find `../dq.ini`. The loader
reads `documents-solr.json` from the current directory. Use `--data_files_dir data`
for another directory relative to the current directory, or supply an absolute
directory path. This does not relocate the reusable schema/configuration recipes. Schema/configuration
recipes remain in `generate-test-collection/`. By default,
this submits to `dq-demo`, creating it with its own `_default` configset copy if
needed. Existing IDs are replaced; other records remain. IDs are stable sequential
strings (`demo-000001`, etc.). Loading fewer documents does not remove higher IDs.
Use `--recreate_collection` to delete all existing demo records and rebuild its
collection, configset, and schema before loading. Existing collections retain
their schema/configuration during ordinary submissions. Recreation refuses to
delete a configset shared by another collection. The loader accepts only localhost targets.
It does not modify `dq.ini` or `my-files`. `schema-solr.json` defines the demo fields.
The script copies `_default` and preserves its normal update processing,
including removal of empty-string values. No additional Solr configuration
is required. The separate `dq-demo` configset persists in ZooKeeper.

### Optional empty-string preservation

Normal submissions use Solr's blank-removal processor. For special tests, use:

```bash
./submit-to-solr.py --submit --preserve_empty_strings
# Or rebuild first:
./submit-to-solr.py --recreate_collection --preserve_empty_strings
```

This preserves empty strings by replacing the demo's blank-removal processor
with a logging processor. No separate configuration JSON is needed. Each
submission explicitly sets the mode: omitting the flag restores normal blank
removal. The mode persists in Solr until changed; it is not limited to one request.
Changing the mode does not rewrite existing records, but the accompanying
submission replaces records with matching IDs. The script refuses to change a
configset shared with another collection.

With normal processing, empty strings may appear as missing/null after ingestion;
whitespace-only strings can remain. The source answer key describes submitted
values, not necessarily what Solr retains.

## Try DQ

```bash
../bin/dq --main_url http://localhost:8983/solr/dq-demo --report quick_checkup
../bin/dq --main_url http://localhost:8983/solr/dq-demo --report full_checkup
../bin/dq --main_url http://localhost:8983/solr/dq-demo --rule missing_fields --action csv --include_field email_t
../bin/dq --main_url http://localhost:8983/solr/dq-demo --rule email --action csv --include_field email_t
```

The normal configured credentials still apply. Reports are written to `reports_dir` (default: `reports/` under the current
working directory). A relative INI setting is resolved from the INI directory. CSV currently goes to stdout; use shell redirection to save it.
For a 100-document fixture at 20% incorrect, each email/phone/SSN regex produces 20 failure rows:
four malformed, four all-whitespace, and twelve null/missing values after
Solr removes the four submitted empty strings. Shared checks handle blank/null values before regex evaluation. Empty-fields CSV produces 16 rows per field: twelve
null/missing and four all-whitespace strings with default blank removal. Solr does not
preserve the distinction between an omitted field and an explicit null.

The main DQ report processors currently support Solr. Elasticsearch and OpenSearch
index creation and loading are available below; DQ reports for those engines remain planned.

### Choose a data directory

Both scripts use `--data_files_dir` (also `--data-files-dir`). The default is the
current directory. Relative paths start there; absolute paths are used as given.

```bash
./generate-test-data-solr.py --count 1000 --data_files_dir data
./submit-to-solr.py --submit --data_files_dir data
```

The generator writes `documents-solr.json` and `expected-results.json` there. The loader reads
`documents-solr.json` there; it does not need the answer key. Connection configuration
still follows normal `dq.ini` discovery from the working directory.

## Elasticsearch and OpenSearch quickstart

Use `submit-to-es.py` for **both Elasticsearch and OpenSearch**, including
free/open-source and commercial Elasticsearch editions. Throughout these
commands and filenames, “ES” is shorthand for that shared workflow. From this
directory, generate the shared data once:

```bash
./generate-test-data-es.py --count 1000 --incorrect_percent 20
```

Submit to local Elasticsearch:

```bash
./submit-to-es.py --submit --main_url http://localhost:9200
```

Or submit the same data to local OpenSearch:

```bash
./submit-to-es.py --submit --main_url http://localhost:9201
```

Elasticsearch and OpenSearch use the same generated data, schema, and loader logic
for the basic API operations used here. The generator writes `documents-es.ndjson`
(Bulk API action/document pairs) and `expected-results.json` in the current directory.
The shared loader uses `schema-es.json`; Solr uses `schema-solr.json` and
`documents-solr.json`. Each generator replaces the answer key in its output directory;
use separate `--data_files_dir` directories, or identical seeds/options, when retaining
fixtures for both formats.

Defaults are server `http://localhost:9200` and index `dq-demo`. Both engines
normally use port 9200; our local OpenSearch instance uses 9201 so they can run
together. Set `--main_url` or INI `main_url` to the desired server. Text fields retain the `_t` suffix
and map to `text`; `id` maps to `keyword`, and `event_date_dt` to `date`.
Original values are retained in `_source`, including nulls, empty strings and whitespace.

The loader accepts `--submit` or `--recreate_index` (required), `--index NAME`,
`--main_url URL`, `--data_files_dir DIR`, `--config FILE`, `--username`, `--password`,
and `--trust_certificate FILE`. Recreation deletes the selected index before loading.
Ordinary submission replaces matching IDs and keeps other records. Bulk requests
are bounded to 500 records/5 MiB and every item is checked for errors. No arguments
shows usage and input-file information without contacting a server.

The parent `dq.ini` is discovered automatically. The `[elasticsearch]` section
supplies connection settings for **either engine**; Solr credentials are never
inherited. For older configuration files, `[opensearch]` is accepted only when
`[elasticsearch]` is absent (its default URL is `http://localhost:9201`). If both
sections exist, `[elasticsearch]` wins. To store different connection settings
for each server, use separate INI files with `[elasticsearch]` and select one
with `--config FILE`. Changing `--main_url` alone keeps the selected file's
credentials and trusted certificate settings. Supported keys are `main_url`, `username`, `password`, and
`trust_certificate`. CLI values override INI settings; certificate paths from INI
are relative to that file. Examples are in `../dq.ini.template`.

See [native server setup](../docs/local-search-engines.md) for startup/shutdown.
Elasticsearch and OpenSearch share this test-data workflow; that does not imply
that all features of the two products are interchangeable.
