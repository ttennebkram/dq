DQ v2
-----

DQ v2 is a Search Engine Data Quality Toolkit for Apache Solr, Elasticsearch, and OpenSearch. GitHub repository: [https://github.com/ttennebkram/dq](https://github.com/ttennebkram/dq).

DQ is a command-line tool: you use it by typing commands in a terminal window.
That can be Terminal on macOS, a terminal on Linux, or Windows Terminal running
PowerShell or Command Prompt on Windows.

## Contents

- [Warning](#warning)
- [Quickstart](#quickstart)
- [Generate a Test Collection](#generate-a-test-collection)
- [Automatic Checkup](#automatic-checkup)
- [Basic Usage](#basic-usage)
- [Rules, Reports and Actions](#rules-reports-and-actions)
- [Using the DQ Tool](#using-the-dq-tool)
- [Windows Users](#windows-users)
- [Using HTTPS](#using-https)
- [Vocabulary](#vocabulary)
- [FAQ](#faq)
- [Development and Custom Rules](#development-and-custom-rules)
- [License and Copyright](#license-and-copyright)
- [More Help](#more-help)

## Warning

Collection/index fields may contain sensitive data, such as email addresses,
phone numbers, or Social Security numbers (SSNs). Reports and CSV exports can
contain those field values, so please exercise appropriate caution when handling
those files.

## Quickstart

If you don't have the project already, choose one of the two methods below to get it.
Both start in your development directory (`~/dev` in these examples).

### Option 1: Clone From Git

Go to your development directory:

```sh
cd ~/dev
```

Clone the project from GitHub:

```sh
git clone https://github.com/ttennebkram/dq.git
```

Then enter the project directory:

```sh
cd dq
```

### Option 2: Download a Zip File

Alternatively, download the project as a ZIP; Git is not required. The ZIP
contains the project's committed files, without the `.git` directory or Git
history. Start in your development directory:

```sh
cd ~/dev
```

Download the project's default branch, `main`, as `dq-main.zip` in the current
directory:

```sh
curl \
    --fail \
    --location \
    --output dq-main.zip \
    https://github.com/ttennebkram/dq/archive/refs/heads/main.zip
```

You can also use **Code > Download ZIP** on the DQ's GitHub page.

Unzip the download:

```sh
unzip dq-main.zip
```

Rename the extracted `dq-main` directory to `dq` to match the examples below:

```sh
mv dq-main dq
```

Then enter the project directory:

```sh
cd dq
```

### Configuration

The report examples in this Quickstart assume you've already created our
standard `dq-demo` test collection. Creating it is described in
[Generate a Test Collection](#generate-a-test-collection), the section
directly below this Quickstart.
To run against your own data, use `--collection NAME` or its synonym
`--index NAME`.

See [Vocabulary](#vocabulary) for equivalent Solr, Elasticsearch, OpenSearch,
and DQ terms such as collection/index and document/record.

Start with the wizard to save your connection settings in `dq.ini`. For a new
setup, it suggests `http://localhost:8983/solr` and collection `dq-demo`, the name
used by the test-data loader. The URL prompt also shows an ES/OpenSearch
example, `http://localhost:9200`, using their default port, 9200. Existing
settings and CLI values take precedence; a collection included in the URL
is used without a separate collection setting:

```sh
bin/dq --config_wizard
```

`--setup_wizard` is a synonym for `--config_wizard`.

The welcome header shows the full path of the file it will create or update.
The default is `dq.ini` in your current directory. To choose a different file,
cancel with Ctrl-C and run:

```sh
bin/dq --config_wizard
```

The wizard asks for the URL, collection, and optional login, then asks for
confirmation before saving.
The wizard preserves saved values and accepts explicit CLI overrides. Enter keeps
a default; `-` clears an optional value.
Leave the username blank if you are not using Basic authentication; the wizard
will skip the password prompt. Blank is the default when no username is saved or supplied. Enter keeps a saved username;
use `-` to clear it and its password when disabling Basic authentication.
Passwords are hidden during entry but stored as plaintext in the INI file.

You can save settings with `--write_config` or edit `dq.ini` directly.
A minimal file looks like this:

```ini
[dq]
main_url = http://localhost:8983/solr
collection = dq-demo
```

The URL may instead include the collection; then omit `collection`. Supplying
it in both places is an error. `--index` is an alias for `--collection`.
Command-line settings override saved values in dq.ini.

DQ searches the current directory and its parents for the nearest `dq.ini`.
Use `--config FILE` to select another file; it must
exist unless you are writing it with `--write_config` or `--config_wizard`.
Both configuration commands default to `dq.ini` in the current directory unless overrode
by `--config FILE` as their destination. Changed old settings are retained as comments.

See [dq.ini.template](dq.ini.template) for all supported settings,
including credentials and certificate paths, and the
[configuration reference](docs/configuration.md) for detailed examples.

### Run DQ

This Quickstart assumes you are running commands from the main `dq` directory,
where the main `README.md`, `bin/`, and `reports/` are located. Using a separate working directory is
also possible and recommended; this is covered later in
[Setting the DQ PATH](#setting-the-dq-path).

Our scripts require Python 3.4.10 or newer. Linux/macOS launchers use `python3`
on PATH; the Windows launcher uses `py -3` (see [Windows Users](#windows-users)).

The main executable is called `dq` in the `bin` directory. You can run it with
no arguments to get syntax usage. From the main `dq` directory, run:

```sh
bin/dq
```

This will display syntax usage information.

On Windows, run:

```bat
bin\dq.cmd
```

Use this Windows launcher wherever the remaining examples show `bin/dq`.
See [Windows Users](#windows-users) for Python installation and PATH setup.

To run `dq` from your own working directory, add the DQ project's `bin` directory
to your PATH; see [Setting the DQ PATH](#setting-the-dq-path).

### Run a Quick Checkup

After saving your connection settings, run:

```sh
bin/dq --report quick_checkup
```

Open `reports/quick_checkup.md` in your Markdown viewer for field-presence
counts and suggested checks. See [Automatic Checkup](#automatic-checkup) for
more detail and the `full_checkup` report.

## Generate a Test Collection

This tool can generate fake/synthetic data and insert it into Solr or Elasticsearch (ES),
including OpenSearch. The default collection/index is named `dq-demo`, which
the Quickstart examples below assume you're using. If you prefer to
work with your own data, you can skip this section.

The scripts in `generate-test-collection/` generate test data with fake names,
addresses, email addresses, phone numbers, SSN-shaped values, dates, and Unicode
cases, then load it into a test collection or index. See
[generate-test-collection/README.md](generate-test-collection/README.md) for the
generation and loading instructions.

Text fields are stored and indexed with the `_t` suffix.
Set an incorrect-value percentage with `--incorrect_percent`,
so that some records will have invalid values.
This mistake percentage will be applied to all generated fields.
A separate answer key records each injected defect.

From the main DQ project directory, go to `generate-test-collection/`:

```sh
# in main dq directory
cd generate-test-collection
```

Run the generator without arguments to display syntax and examples. This does
not generate or overwrite any files:

```sh
./generate-test-data-solr.py
```

Or on Windows do:

```cmd
.\generate-test-data-solr.cmd
```

Running with no arguments will show the syntax.

Example: Generate 1,000 records with a 20% incorrect-value setting.
`--count` is required; 1,000 is a suggested starting size:

```sh
./generate-test-data-solr.py --count 1_000 --incorrect_percent 20
```

--count can be 1000 or 1_000.  The underscore notation works in this code even with Python 3.4

Check the generated data file:

```sh
ls -l documents-solr.json
```

The generator writes `documents-solr.json` and `expected-results.json` to the
current working directory by default.
There is also a `--data_files_dir` option
to use a different directory for `documents-solr.json` or `documents-es.ndjson`.
Reusable setup files and instructions remain in `generate-test-collection/`.
Generated JSON is ignored by Git.

Create the Solr collection if needed:

```sh
./submit-to-solr.py --recreate_collection
```

Then submit the generated records:

```sh
./submit-to-solr.py --submit
```

Run a quick checkup on the test collection:

```sh
../bin/dq --report quick_checkup
```

The loader finds the parent `dq.ini` automatically. Generated JSON stays in the
current directory; reports use `reports_dir`.

The loader resubmits matching IDs by default. To rebuild the test collection
and configset, removing its old records before loading, run this from the same
`generate-test-collection/` directory:

TODO: what goes here?

**Test-data generation is random by default.** Omit `--seed` for a fresh run;
use `--seed N` to reproduce one with the same options and generator/Python
version. Every chosen seed is printed and saved in `expected-results.json`. Seeds `0`
and `-1` are repeatable integer seeds, not special random modes.

For special empty-string tests, enable preservation when submitting:

```sh
./submit-to-solr.py --submit --preserve_empty_strings
```

Normally omit this flag: each submission restores standard Solr blank removal
unless preservation is explicitly requested. No configuration JSON file is needed.

For Elasticsearch and OpenSearch test indexes, stay in the same directory and
generate the shared ES data file:

```sh
./generate-test-data-es.py --count 1_000
```

Check the generated file:

```sh
ls -l documents-es.ndjson
```

Create the index if needed:

./submit-to-es.py --recreate_index

And submit the generated records:

```sh
./submit-to-es.py --submit
```

The same submission command supports OpenSearch. To use the local instance on
port 9201:

```sh
./submit-to-es.py --main_url http://localhost:9201 --submit
```

Both engines share `documents-es.ndjson`, `schema-es.json`, and the basic loader
API logic. Solr uses `documents-solr.json` and `schema-solr.json`.
See the [test collection quickstart](generate-test-collection/README.md#elasticsearch-and-opensearch-quickstart)
and [native server setup](docs/local-search-engines.md).
The shared ES/OpenSearch loader accepts `--main_url`, `--index`, `--data_files_dir`,
`--config`, `--username`, `--password`, `--trust_certificate`, and either
`--submit` or `--recreate_index`. It reads connection keys from the
`[elasticsearch]` INI section for either engine; CLI overrides those values.
A legacy `[opensearch]` section is used only when `[elasticsearch]` is absent.
With no configured URL, the default is `http://localhost:9200` (9201 for a legacy
OpenSearch-only section). Use separate INI files when the servers need different credentials.
DQ can list fields, run checkups, and apply stored-value rules to these indexes.

## Automatic Checkup

These examples assume basic connection parameters are stored in `dq.ini`.

```sh
bin/dq --report quick_checkup
bin/dq --report full_checkup --include_field email_t --rows 1_000
```

| Report | What It Does | Main Output |
| ------ | ------------ | ----------- |
| `quick_checkup` | Counts field presence and suggests rules without fetching stored values. | `reports/quick_checkup.md` |
| `full_checkup` | Scans stored values and runs the selected rules. | `reports/full_checkup.md`, linked field details, and CSV findings |

`full_checkup` can be slow on large datasets. Use `--include_fields` to focus on
critical fields and `--rows` / `--size` to limit test runs. See
[Checkup Reports](docs/configuration.md#checkup-reports) for output details and
[Scan Progress](docs/configuration.md#scan-progress) for progress settings.

### Automatic Rule Selection

DQ looks at the name and base type of each field to decide what rules to
automatically apply. You can always apply a specific rule to a specific field
with the command-line options `--rule <RULE_NAME> --include_field <FIELD_PATTERN>`.

See [Automatic Field Name and Type Matching](#automatic-field-name-and-type-matching)
for the field name to rules matching table.

## Basic Usage

These examples assume you are in the main DQ directory, for example
`~/dev/dq/`, and that core configuration values are stored in `dq.ini`.

Run without arguments to display detailed usage and the command roadmap:

```sh
bin/dq
```

Select a rule, a special report, or a utility command:

```sh
bin/dq --list_fields --main_url URL --collection NAME
bin/dq --list_fields
bin/dq --list_reports
bin/dq --list_rules
bin/dq --report NAME [NAME ...]
bin/dq --rule NAME [NAME ...]
bin/dq --write_config
bin/dq --config_wizard
bin/dq --help
bin/dq --version
```

The later commands assume the remaining parameters are read from `dq.ini`.

Rule commands default to the CSV action. Reports and rules cannot be combined in one run. Add field-filter options as needed.

Select a Markdown report by name:

```sh
bin/dq --report quick_checkup
```

``--report`` and ``--reports`` are synonyms.

See [Rules, Reports and Actions](#rules-reports-and-actions) for the complete report and CSV
reference.

### Run a Report

Output files are usually named `reports/<REPORT_NAME>.md` for Markdown reports
and `reports/<FIELD_NAME>_<RULE_NAME>.csv` for rule CSV exports.

To create the quick collection-wide report, run:

```sh
bin/dq --report quick_checkup
```

Open `reports/quick_checkup.md` in your Markdown viewer. To list fields instead:

```sh
bin/dq --list_fields
```

To export documents without a value for one stored field:

```sh
bin/dq --rule missing_fields_base --include_field email_t
```

This writes `reports/email_t_missing_fields_base.csv` automatically. Replace `email_t` with
your field name when using your own data. Field listing writes to standard output.
See [Using HTTPS](#using-https) for certificates and authentication.

### Export Missing, Empty, or Whitespace Values

The `missing_fields_base` rule exports documents without a stored field value:

```sh
bin/dq --rule missing_fields_base --include_field email_t
```

This creates `reports/email_t_missing_fields_base.csv` with columns
`id,reason,value`. Missing values are reported as `missing or null`
because Solr does not distinguish those cases after indexing.

Use separate rules for zero-length and whitespace-only stored strings:

```sh
bin/dq --rule empty_strings_base --include_field email_t
bin/dq --rule whitespace_only_base --include_field email_t
```

`empty_strings_base` selects zero-length strings. `whitespace_only_base` requires at least
one whitespace character, so the two rules do not overlap. Standard CSV quoting
preserves spaces, tabs, and line breaks. Field announcements and progress dots
go to stdout; configuration, export completion, and errors go to stderr.

`missing_fields_base` always checks records through the normal cursor scan. When it
runs by itself, DQ requests an `exists(field)` Boolean for each selected field
instead of transferring the stored values. With `--rows N`, it checks the first
N source documents in unique-key order. When `missing_fields_base` is combined with
other rules, DQ fetches the values once in one shared record scan and applies
every rule in command-line order:

```sh
bin/dq --rules missing_fields_base whitespace_only_base --include_field notes_t
```

This reports a missing value first; a present value continues to the
`whitespace_only_base` rule. As with other combined rules, only the first failed rule
is exported for each value.

Select one or more stored fields with `--include_field[s]` and `--exclude_field[s]`.
The CSV action cannot be combined with `--report`, `--list_fields`, `--write_config`, or
`--config_wizard`. The `id` column uses the schema's unique key.

DQ scans the unique key and selected stored fields together using Solr `cursorMark`, in
pages of 1,000 documents. Output is streamed in bounded batches. No matches
produces just the header. Missing fields, explicit nulls, and empty arrays are
reported as `missing or null`: Solr commonly omits null values, so their original
form cannot be distinguished. Zero and false are not missing.

Vector fields remain presence-only: missing vectors produce `null` rows without
fetching vector arrays.
Cursor paging is not a snapshot: avoid indexing or deleting during an export
when you need a consistent result. Partial Solr responses and request failures
stop the export with a nonzero exit status; any output already written is
incomplete. Check the exit status before using the CSV file.

List the fields in a Solr collection:

```sh
bin/dq --list_fields
```

The command above uses the project's ``dq.ini`` file. Both target values have
named command-line options that match the configuration keys:

```sh
bin/dq --list_fields \
    --main_url http://localhost:8983/solr \
    --collection my-files
```

The hyphenated spelling is retained as an alias:

```sh
bin/dq --list-fields \
    --main_url http://localhost:8983/solr \
    --collection my-files
```

The output is sorted by field name and includes concrete fields present in the
index, each field's type, stored, indexed, doc-values, and multi-valued
properties, the number of documents containing the field, and the dynamic
schema pattern that defines it. Field discovery combines Solr's Luke and Schema
APIs. When Luke does not provide a document count for a point-number, date,
vector, or non-indexed field, DQ uses a field-presence query to obtain the
count instead of leaving the value blank.

### Field Filtering Examples

Field filters use simple, case-sensitive glob pattern matching, not regular
expressions. ``*`` matches any number of characters, ``?`` matches one
character, and bracket expressions such as ``[0-9]`` match one character from
a set or range.

With neither ``--include_fields`` nor ``--exclude_fields``, DQ applies the
default exclusion pattern ``_*_``. This omits Solr internal fields such as
``_version_``, ``_root_``, and ``_nest_path_``. Supplying either option replaces
that default selection rule. Both options accept one or more shell-style
patterns and can be repeated:

```sh
bin/dq --list_fields --include_fields '*_name_t' --include_fields notes_t
```

```sh
bin/dq --list_fields --include_fields '*_name_t' notes_t
```

```sh
bin/dq --list_fields --exclude_fields '_*' --exclude_fields '*_vector'
```

An explicit include can therefore select an internal field when it is needed:

```sh
bin/dq --list_fields --include_fields _version_
```

The final ``s`` is optional: ``--include_field`` and ``--exclude_field`` are
aliases for the plural forms. Hyphenated spellings are also accepted:
``--include-field``, ``--include-fields``, ``--exclude-field``, and
``--exclude-fields``.

Commands whose names begin with ``--list_`` write their results to standard
output. They do not create Markdown reports or other output files. Redirect
standard output when a saved copy is wanted:

```sh
bin/dq --list_fields > fields.txt
```

## Rules, Reports and Actions

DQ can run a report, or apply rules to stored values and perform an action on
the results.

| Concept | Selected With | Purpose |
| ------- | ------------- | ------- |
| Report  | `--report` / `--reports` | Run coordinated analysis and write Markdown plus any supporting files. |
| Rule    | `--rule` / `--rules`     | Whether each selected stored value passes or fails. |
| Action  | `--action`                | Tell DQ what to do with rule results. |

### Reports

| Report          | Output | Description |
| --------------- | ------ | ----------- |
| `quick_checkup` | Markdown | Collection-wide presence counts and suggested checks; no stored-value scan. |
| `full_checkup`  | Markdown and CSV | Runs combined checks and writes field details. **May be slow.** Limit fields with `--include_fields` and documents with `--rows` / `--size`. |

Run `bin/dq --list_reports` to print this report catalog in the terminal.

`--report` and `--reports` are synonyms and accept one or more report names.
Selecting a report implies `--action report`. Selecting one or more rules defaults to `--action csv`; it may still be written explicitly.

### Performance: Full Checkup Scope Limits

`full_checkup` can be very slow on a large collection or index because it scans
every record. During testing, you can limit the number of records with `--rows` (same as
`--size`). The row limit should usually be removed for production runs so every
document is checked. `--include_fields` can also limit the scope by focusing on
specific critical fields; this may or may not be appropriate in production.

Restrict a report to selected fields (these examples assume basic connection
information, including `main_url` and the collection/index name, is stored in
`dq.ini`):

```sh
bin/dq --report full_checkup --include_fields email_t phone_t
```

Restrict the run to just scan 1,000 documents:

```sh
bin/dq --report full_checkup --rows 1_000
```

`--size` is a synonym for `--rows`.

### Rules

Rules run on selected stored field values.

| Rule                    | Type      | Description |
| ----------------------- | --------- | ----------- |
| `missing_fields_base`        | Base      | Field is missing or null. |
| `empty_strings_base`         | Base      | Stored text value contains zero characters. |
| `whitespace_only_base`       | Base      | Nonempty stored string contains only whitespace. |
| `surrounding_whitespace_base`| Base      | Stored string has leading or trailing whitespace. |
| `code_points_base`           | Base      | Stored text contains an unusual Unicode character. |
| `email_base`            | Base      | Email syntax only. |
| `us_phone_base`         | Base      | US phone-number syntax only. |
| `ssn_base`              | Base      | SSN structure only. |
| `part_number_example_base` | Base | Example part-number regex checks. |
| `standard_text_composite` | Predefined Composite | Missing, empty, whitespace, and `code_points_base` checks. |
| `email_composite`       | Predefined Composite | `standard_text_composite`, then `email_base`. |
| `us_phone_composite`    | Predefined Composite | `standard_text_composite`, then `us_phone_base`. |
| `ssn_composite`         | Predefined Composite | `standard_text_composite`, then `ssn_base`. |
| `part_number_example_composite` | Predefined Composite | `standard_text_composite`, then `part_number_example_base`. |

Run `bin/dq --list_rules` to print the rule catalog, including each rule's
Base or Predefined Composite type.

Base rules are named building blocks that can run alone or be combined. A
composite is either a predefined combination such as `email_composite` or a
combination formed dynamically by supplying multiple names with `--rules`.
Composites may contain other composites. DQ recursively flattens them to one
ordered list of base rules, removes duplicates while preserving first occurrence,
and evaluates each base rule at most once per value. DQ exports the first failure.

A base format rule intentionally performs only its regex check. For example,
`email_base` reports a regex failure for a value with trailing whitespace.
`email_composite` reports the more specific `surrounding_whitespace_base` failure
before it reaches `email_base`. A null also fails a base regex unless
`--skip_null_values` is enabled; the composite reports `missing_fields_base` first.

### Actions

| Action   | Used With | Result |
| -------- | --------- | ------ |
| `report` | Reports   | Writes the selected special Markdown report and its supporting files. |
| `csv`    | Rules     | Writes one `id,reason,value` CSV file for each selected field. |

CSV filenames use `<FIELD_NAME>_<RULE_NAME>.csv` in the configured reports
directory. Single-valued fields
produce at most one row per document; multivalued fields can produce one row per
failing value. A file with no findings contains only its header.

### Examples

These examples assume the target is saved in `dq.ini`:

```sh
bin/dq --report quick_checkup
bin/dq --rule missing_fields_base --include_field email_t --rows 1000
bin/dq --rule email_composite --include_field email_t --rows 1000
bin/dq --rules missing_fields_base whitespace_only_base --include_field notes_t
```

Do not combine reports and rule exports in one invocation. Rule, report, and
action selections are command-line options and are not saved in `dq.ini`.

### Other Commands

| Command                              | What It Does                                                        |
| ------------------------------------ | ------------------------------------------------------------------- |
| `--list_fields`                      | List fields, schema properties, and document counts on stdout.      |
| `--list_reports`                     | List reports, status, and descriptions on stdout.                   |
| `--list_rules`                       | List rules, Base and Predefined Composite type, and descriptions.   |
| `--config_wizard` / `--setup_wizard` | Walk through connection settings and save the INI file.             |
| `--write_config`                     | Save effective settings to dq.ini or the file selected by --config. |
| `--help` / `-h`                      | Display syntax, options, and the current report catalog.            |
| `--version`                          | Display the DQ version.                                             |

Hyphenated aliases are also accepted: `--list-fields`, `--list-reports`,
`--list-rules`, `--config-wizard`,
`--setup-wizard`, and `--write-config`. Select one action per invocation;
multiple report names belong to one `--report` action.

## Using the DQ Tool

For regular use, keep `dq.ini` and generated reports in a separate working
directory. You can also run `bin/dq` from the main project directory.

### Use a Separate Working Directory

On either platform, create and enter your preferred working directory, outside
the DQ project directory. This is where you will keep your target configuration
and generated reports.

Follow [Setting the DQ PATH](#setting-the-dq-path) below. Then run `dq` from that working directory to
display usage and save its connection settings with:

```sh
dq --config_wizard
```

The wizard writes `dq.ini` in that working directory. Reports go into its
`reports/` directory by default. Both launchers preserve your working directory
for configuration lookup and report output.

### Override Saved Options

Command-line arguments override the corresponding options in `dq.ini` for
that run. Other settings continue to come from the INI file, so you can keep a
default collection there and temporarily select another one on the command line.
For example, save:

```ini
[DEFAULT]
main_url = http://localhost:8983/solr
collection = dq-demo
```

With `dq` on PATH, use the saved `dq-demo` collection:

```sh
dq --report quick_checkup
```

To check another collection, for example `my-files`, override just its name:

```sh
dq --report quick_checkup --collection my-files
```

The override applies only to that run; `dq.ini` keeps `dq-demo` as the default.
`--index` is a synonym for `--collection`. Keep `main_url` as the server's base
URL, as shown above, when supplying the collection separately. If the saved URL
already includes a collection, override `--main_url` with the desired complete
URL instead. Use `--write_config` when you want to save new defaults.

### Setting the DQ PATH

#### macOS and Linux

On Unix/Linux and macOS, add the project's `bin` directory to PATH to run `dq`
from a separate working directory. Use your actual project location in the
examples below.

For the current terminal session:

```sh
export PATH="$HOME/dev/dq/bin:$PATH"
```

For future login sessions, you can keep that export line in `~/.profile`, a
traditional place for environment settings shared by Bourne-style shells.
Keep shared `.profile` contents compatible with POSIX shell syntax.

Bash login shells read the first available file among `~/.bash_profile`,
`~/.bash_login`, and `~/.profile`, in that order. If either of the first two
exists, have it load `.profile`. Zsh does not read `.profile` automatically;
its login file is `~/.zprofile`. To load a shared `.profile` from the relevant
Bash or Zsh login file, use:

```sh
[ -r "$HOME/.profile" ] && . "$HOME/.profile"
```

Ordinary non-interactive scripts inherit an exported PATH from their parent;
they do not normally read `.profile` themselves. A non-interactive Bash login
shell, such as `bash -lc`, does read the login files using the same precedence.
For jobs started independently by cron, launchd, or another scheduler, configure
PATH explicitly in the job rather than assuming a terminal's login settings.
See [Bash startup files](https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files.html)
and [Zsh startup files](https://zsh.sourceforge.io/Doc/Release/Files.html).

Inside whichever shell configuration file you use, add this line, adjusting the
project path for your installation:

```sh
export PATH="$HOME/dev/dq/bin:$PATH"
```

Save the file. To apply the change in your current terminal, run that same
`export` line there. Then, in Bash, clear any cached location of an older `dq`
command:

```sh
hash -r
```

Check which command will run:

```sh
command -v dq
```

The Unix/macOS launcher uses `python3` on PATH, including an activated virtual
environment.

#### Windows

In PowerShell, add the project's `bin` directory for the current terminal session:

```powershell
$env:Path = "$HOME\dev\dq\bin;$env:Path"
```

To keep the setting for future terminals:

1. Open **Start**, search for **Edit environment variables for your account**,
   and open it.
2. Under **User variables**, select **Path**, then click **Edit**.
3. Click **New** and add your DQ project's `bin` directory, for example
   `C:\Users\you\dev\dq\bin`. Use your actual location; add the directory,
   not the `dq.cmd` filename, and keep the existing entries.
4. Click **OK** to save and close the dialogs, then open a new Command Prompt
   or PowerShell window.

See Microsoft's [environment variable instructions](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables#create-persistent-environment-variables-in-windows)
for more detail.

Check which Windows launcher will run:

```powershell
Get-Command dq.cmd
```

Once that directory is on PATH, you can type `dq` from your own working
directory. Windows finds `dq.cmd`, which uses `py.exe -3` to run DQ.

## Windows Users

Install Python 3 and make sure the Windows Python launcher, `py.exe`, is
available on your PATH. Our Windows wrapper uses `py -3`, so an executable
specifically named `python3` is not required. The `python3` PATH requirement in
the Linux/macOS examples does not apply to this wrapper.

See [Setting the DQ PATH](#setting-the-dq-path) for the Windows PATH steps.

Follow the official [Python on Windows installation guide](https://docs.python.org/3/using/windows.html#installation).
After installation, reopen Command Prompt or PowerShell. Confirm that the
launcher can find Python 3:

```bat
py -3 --version
```

If `py` is not recognized, follow Python's [Windows troubleshooting guide](https://docs.python.org/3/using/windows.html#troubleshooting)
to make the launcher available on PATH. If you already have Python 3 available
as `python`, you can run `python bin\dq.py` directly instead.

### Run DQ on Windows

From the main DQ directory, display usage:

```bat
.\bin\dq.cmd
```

Then configure your connection:

```bat
.\bin\dq.cmd --config_wizard
```

Use `.\bin\dq.cmd` in place of `bin/dq` throughout this README. You can also run
`py -3 bin\dq.py` directly. The wrapper passes all arguments to DQ, preserves
your working directory, and returns DQ's exit status. It uses `py.exe -3` to
select Python 3. The wrapper has Windows CRLF line endings;
execution on Windows has not yet been verified.

### Running Other Python Scripts

The same `py -3` prefix may be needed for other `.py` scripts shown in this
README or the scripts' usage messages. For example, from the
`generate-test-collection` directory, replace `./generate-test-data-solr.py`
with:

```bat
py -3 generate-test-data-solr.py --count 1000
```

Likewise, submit the generated data with:

```bat
py -3 submit-to-solr.py --submit
```

Some Python files start with `#!/usr/bin/env python3`, a launcher line used on
Linux/macOS. Using `py -3 script-name.py` explicitly selects Python 3 on Windows;
you do not need to edit that line or rely on `.py` file associations.

## Using HTTPS

HTTPS uses TLS (Transport Layer Security) to encrypt the connection and
authenticate the server. Enabling HTTPS on Solr/ES is called configuring TLS.

Set `main_url` to an `https://` URL. DQ verifies the certificate and hostname
using Python's default trusted certificates.

DQ uses exactly the protocol specified in `main_url`. It never switches from
HTTP to HTTPS or from HTTPS to HTTP, including server redirects. A redirect
that changes protocol produces an error; there is no automatic fallback.
Same-protocol redirects remain allowed for unauthenticated requests.

HTTPS client support does not enable HTTPS on Solr. Solr itself must be configured
with a server certificate and private key before changing its URL to `https://`.

### HTTP Basic Authentication

HTTP Basic authentication can be configured with `--username` and `--password`,
or saved in the INI file:

```ini
[dq]
main_url = https://localhost:8983/solr
collection = my-files
username = mark
password = replace-with-your-password
```

CLI values override the corresponding INI values. Username and password must be
supplied together. Passwords are literal, including `%` characters. No new
authentication environment variables are used.

The INI file stores the password in plaintext. Prefer it to `--password` on the
command line, which can appear in shell history or process listings. Use HTTPS
for encrypted credentials in transit. URLs containing embedded credentials are
rejected. Authenticated redirects are refused to avoid forwarding credentials.

`--write_config` saves these settings and creates the resulting file with
owner-only permissions (0600 on Unix). An updated password replaces the old one
without retaining it in a comment. Passwords are redacted in the report's
Options Used section and excluded from authenticated HTTP error response bodies.
Keep custom config filenames out of version control too; `.gitignore` already
excludes `dq.ini`. For a manually created INI, run `chmod 600 dq.ini`.

### Using a Self-Signed Certificate

The `trust_certificate` option configures certificate trust in DQ.
**For HTTPS, you only need the `trust_certificate` option if Solr/ES is using a self-signed certificate.**
It adds trust for a self-signed server certificate or a private CA that Python
does not already trust. Python's certificate store may differ from the macOS
Keychain.

For a private certificate authority or a self-signed Solr certificate:

```sh
bin/dq --report quick_checkup --trust_certificate certificates/solr-ca.pem
```

`--trust-certificate` is an alias. Supply a PEM file containing the trusted CA
certificate, or the server's public certificate if self-signed. A certificate
name alone is insufficient. This adds trust without disabling hostname checks.
DQ does not need the server's private key. Client-certificate authentication
(mutual TLS) and certificate-fingerprint pinning are not implemented.

To save the certificate path in `dq.ini`:

```ini
[dq]
trust_certificate = certificates/solr-ca.pem
```

Certificate paths from INI are relative to that INI file; command-line paths
are relative to the current directory. The following steps show how to create
and export a self-signed certificate for a local Solr installation.

#### Create a Local Self-Signed Solr Certificate

Solr needs a keystore containing its server certificate and private key. DQ
needs only the public certificate, exported as PEM. These steps use the local
Solr installation below and require the JDK's `keytool` command.

For a new keystore, create a certificate valid for 3,650 days (about ten years):

```sh
cd ~/dev/solr-9.10.1
mkdir -p server/etc/certificates
chmod 700 server/etc/certificates

keytool -genkeypair \
  -alias solr-local \
  -keyalg RSA \
  -keysize 2048 \
  -validity 3650 \
  -storetype PKCS12 \
  -keystore server/etc/certificates/solr-local.p12 \
  -dname "CN=localhost" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1,IP:::1"
```

Choose a keystore password at the prompt. Solr's documentation uses `secret`
for its local HTTPS example; this is not a default Solr login password. Keep the
keystore password for the server's HTTPS configuration. The certificate covers
`localhost`, IPv4 loopback (`127.0.0.1`), and IPv6 loopback (`::1`).

Do not repeat `-genkeypair` for an existing `solr-local` alias. If the certificate
was already created with `-validity 365`, reissue the self-signed certificate
using the existing key and a longer validity period:

```sh
keytool -selfcert \
  -alias solr-local \
  -keystore ~/dev/solr-9.10.1/server/etc/certificates/solr-local.p12 \
  -validity 3650 \
  -ext "SAN=DNS:localhost,IP:127.0.0.1,IP:::1"
```

#### Export the Public PEM File

Export after creating or reissuing the certificate, entering the same keystore
password when prompted:

```sh
keytool -exportcert -rfc \
  -alias solr-local \
  -keystore ~/dev/solr-9.10.1/server/etc/certificates/solr-local.p12 \
  -file ~/dev/solr-9.10.1/server/etc/certificates/solr-local.pem
```

This exports the public certificate only, without the private key. To inspect
its validity dates and subject alternative names:

```sh
keytool -printcert \
  -file ~/dev/solr-9.10.1/server/etc/certificates/solr-local.pem
```

#### Reference the PEM from the DQ Project

Reference the certificate directly in `~/dev/dq/dq.ini`, under its existing
`[DEFAULT]` or `[dq]` section. No copy or symlink in the project is necessary:

```ini
trust_certificate = ~/dev/solr-9.10.1/server/etc/certificates/solr-local.pem
```

The project's `dq.ini` is ignored by Git. Keeping one PEM file means subsequent
DQ runs use the updated certificate after it is re-exported to the same path.
The certificate file does not contain, and DQ does not need, the keystore password.

Certificate creation and export do not enable an HTTPS listener. The intended
local arrangement is HTTP on port 8983 and HTTPS on port 8984, serving the same
collection. Configuring Solr's listeners is a separate server setup step.
After the HTTPS listener is configured, the DQ target settings would be:

```ini
main_url = https://localhost:8984/solr
collection = my-files
trust_certificate = ~/dev/solr-9.10.1/server/etc/certificates/solr-local.pem
```

Then run `bin/dq --report quick_checkup`. DQ will use HTTPS exactly as specified;
it will not switch protocols. Trusting this PEM in DQ does not install it into
the browser's certificate store.

See the [Solr HTTPS documentation](https://solr.apache.org/guide/solr/9_10/deployment-guide/enabling-ssl.html)
for the keystore and server configuration reference.

### Install the Optional Solr Helper

DQ distributes `solr-auth.py` in [aux-bin/](aux-bin/README.md). Copy it into the
Solr installation before using it. It is a standalone helper and does not
require DQ to be installed or remain at its current path.

Recommended location: `local-scripts/` under the Solr installation. From the
DQ project directory:

```sh
mkdir -p ~/dev/solr-9.10.1/local-scripts
cp aux-bin/solr-auth.py ~/dev/solr-9.10.1/local-scripts/solr-auth.py
chmod +x ~/dev/solr-9.10.1/local-scripts/solr-auth.py
```

Alternatively, copy it into Solr's existing `bin/` directory:

```sh
cp aux-bin/solr-auth.py ~/dev/solr-9.10.1/bin/solr-auth.py
chmod +x ~/dev/solr-9.10.1/bin/solr-auth.py
```

You can also copy it directly into the Solr installation root. The helper
detects the installation from its own location in any of these three layouts.
Use `--solr_dir DIR` to specify the installation explicitly when running it
from elsewhere, including directly from DQ's `aux-bin/`.

Choose one installed location. The examples below use `local-scripts/`; use
`bin/solr-auth.py` or `./solr-auth.py` instead if you chose another location. After
updating the helper in DQ, repeat the copy to update your installed copy.
Copying the script does not change authentication or overwrite the saved login.
The password file is always `local-auth.ini` in the selected Solr installation
root, never in DQ's `aux-bin/`.

### Switch Local Solr Basic Authentication On or Off

The development server normally runs without a login. Use the helper in the Solr installation when testing authentication:

```sh
cd ~/dev/solr-9.10.1
./local-scripts/solr-auth.py status
./local-scripts/solr-auth.py on
./local-scripts/solr-auth.py off
```

On the first `on`, the helper prompts for a username and password and saves them
in plaintext in `local-auth.ini` under the Solr installation, with owner-only
permissions. Later `on` commands reuse that login without prompting. `off` keeps
the saved login for next time. This is separate from the certificate keystore
password. To replace the saved login, first turn authentication off, then run:

```sh
./local-scripts/solr-auth.py on --set_credentials
```

The helper passes the saved login to Solr's native `--credentials` option, so it
can briefly appear in a local process listing. This convenience is intended for
this local test installation. The helper does not print the saved password.

`off` invokes the native disable command, returning to anonymous
local access. The change applies to both HTTP and HTTPS listeners; the helper
does not change protocols, TLS configuration, certificates, or collection data.

SolrCloud applies security changes live through ZooKeeper, so a restart is
normally unnecessary. To explicitly restart as part of the switch:

```sh
./local-scripts/solr-auth.py on --restart
./local-scripts/solr-auth.py off --restart
```

The helper lives in the Solr installation's `local-scripts/` directory and targets
that installation by default, port 8983,
and embedded ZooKeeper on loopback port 9983. Solr must already be running.
Use `--solr_dir DIR` and `--port PORT` if those local defaults change. Restart
uses SolrCloud mode and advertises localhost; keep persistent listener settings
in the Solr installation's configuration files. This is a local development
helper, not a general cluster administration tool.

Before changing authentication, the helper saves `security.json`, `solr.in.sh`,
and any existing `basicAuth.conf` under the Solr installation's
`local-auth-backups/`, with owner-only permissions. Solr's native disable command
also removes authorization settings; the backup retains the prior configuration.
The helper refuses to replace non-Basic authentication plugins. Enabling an
already configured authentication plugin is also refused.

The helper does not edit `dq.ini`. Use the chosen login in DQ when authentication
is on; omit the `username` and `password` settings during normal unauthenticated
local testing. Keep anonymous Solr access restricted to the local machine.

The saved login file is
`~/dev/solr-9.10.1/local-auth.ini`.
The installed helper runs independently of DQ; its distributable source is in
DQ's `aux-bin/`.

## Vocabulary

DQ uses common terms across Solr, Elasticsearch, and OpenSearch:

| Terms | Meaning |
| ----- | ------- |
| **Document**, **record** | The same thing in DQ: one searchable item in the target dataset. Search APIs commonly use *document*; progress and performance output may use *record*. |
| **Collection**, **index** | The same concept: the named target dataset. Solr uses *collection*; Elasticsearch and OpenSearch use *index*. |
| **Document ID**, **unique key** | The value that uniquely identifies a document. Solr schema metadata calls it the *unique key*. |
| **Field** | A named value within a document. A field may be single-valued or multivalued, stored or indexed. |
| **Regex** | Short for *regular expression*: a text pattern used to identify values that match a particular format. |
| **Rows**, **size** | Synonyms for DQ's maximum number of documents to scan. The command-line options are `--rows` and `--size` and they are synonyms. |
| **Rule** | A requirement applied to field values. When rules are stacked, a value must pass all of them. |
| **Action** | What DQ does with rule results, such as writing CSV output. |
| **Report** | A special analysis that may coordinate several checks and create Markdown, CSV, links, or supporting files. |

## FAQ

### Why Use INI Instead of YAML, JSON, or XML?

INI keeps settings easy to read and edit, supports comments, and is built into
Python 3.4 through `configparser`. YAML would require an additional dependency.
JSON is too verbose for these hand-edited settings and has no standard comment
syntax. XML is also verbose and feels old-school for a small configuration file.
INI lets DQ retain its no-runtime-dependencies design and older Python support.

Regex patterns live separately in plain-text `.regex` files, preserving readable
extended syntax without configuration-file escaping. Rule INI files contain
the settings and references; relative regex paths resolve against their INI file.

### What Does an Underscore in a Number Mean?

An underscore can group digits to make a large number easier to read. For
example, `1_000` means 1000 and `2_000_000` means 2000000. Python calls this
feature **underscores in numeric literals**. It was added to Python 3.6 by
[PEP 515](https://peps.python.org/pep-0515/).

Python 3.4 cannot use syntax such as `number = 1_000` inside Python source code.
DQ can still accept `--rows 1_000`, `--size 1_000`, and `rows = 1_000` in
`dq.ini` while running on Python 3.4 because those values arrive as text. DQ
validates the text and removes the grouping underscores before converting it to
an integer. Use only one underscore between digits; leading, trailing, and
repeated underscores are rejected.

### Can Solr Distinguish a Missing Field From a Null Field?

Not after ordinary indexing. If a source document omits a field, Solr stores no
value for it. If the source submits that field as null, Solr also stores no value
and normally omits the field from query responses. Setting a field to null in an
atomic update removes its values. Therefore, `missing_fields_base` reports **not
submitted or null**; it cannot determine which source condition occurred.

Applications that need that distinction must record it while ingesting data,
for example with a companion Boolean field such as `email_was_null_b`, a chosen
sentinel value, or a retained copy of the original source document.

## Development and Custom Rules

### Requirements and Dependencies

Required software:

* Python 3.4.10 or newer

Dependencies: No runtime or development dependencies; DQ uses only the Python standard library.

### Internal Rule and Report Modules

Rules live under `src/dq/rules/`. Built-in Markdown reports and their shared
formatting live under `src/dq/reports/`. These report packages are part of DQ
itself. The MVP does not support user-defined custom reports or load report code
from outside the source tree. See
[Internal Rules and Reports](docs/report-modules.md) for the package layout and
handler interfaces used by DQ development.

### Custom Rules

Custom rules are defined under `src/dq/rules/`. Every public rule
gets its own package directory. Base-rule directory names end in `_base`, and
predefined composite-rule directory names end in `_composite`. A regex base rule
keeps its settings in `rule.ini` and its extended regular expression in a
separate `.regex` file.

The bundled part-number example demonstrates both rule types.

#### Custom Regex Rule Example

`part_number_example_base` is a regex base rule that matches three letters, a
dash, and six digits, such as `ABC-123456`. Its options are explained in the
comments in `dq/src/dq/rules/part_number_example_base/rule.ini`.

| File | Purpose |
| ---- | ------- |
| `__init__.py` | Marks the directory as a Python rule package. |
| `rule.ini` | Configures the directory-named rule and its numbered `[regex:regex01]` check. |
| `part_number_example.regex` | Contains the extended regular expression for the part-number format. |

Run the base rule when only that format check is wanted:

```sh
bin/dq --rule part_number_example_base --include_field part_number_t --rows 1_000
```

To keep missing or null fields out of the CSV file, add
`--skip_null_values true`:

```sh
bin/dq --rule part_number_example_base --include_field part_number_t --rows 1_000 --skip_null_values true
```

This reports only actual string values that do not match the part-number regex.
Empty and whitespace-only strings are still strings, so this base rule reports
them when they do not match.

#### Custom Composite Rule Example

`part_number_example_composite` is a predefined composite rule. It performs the
same preliminary tests as `standard_text_composite`, then checks the value
against a custom regular expression.

| File | Purpose |
| ---- | ------- |
| `__init__.py` | Defines the composite metadata and its ordered `RULES` chain. |

```python
RULES = ('standard_text_composite', 'part_number_example_base')
```

DQ therefore reports standard text problems, such as missing values or
surrounding whitespace, before applying the part-number format check:

```sh
bin/dq --rule part_number_example_composite --include_field part_number_t
```

### Automatic Field Name and Type Matching

DQ identifies text/string fields from search-engine metadata rather than relying
on `_t` or `_s` name suffixes. For Solr, it reads the schema field type and its
underlying field-type class. For Elasticsearch and OpenSearch, it reads the index
mapping and recognizes string types such as `text` and `keyword`.

Most text/string fields receive `standard_text_composite`, unless the field name
implies a special type such as an email address, phone number, or Social Security
number. DQ applies the corresponding specialized composite rule to those fields.
A matching name on a numeric, date, Boolean, or vector field does not trigger a
text or Regex rule. Currently, this automatic selection is not easy to override.

DQ converts field names to lowercase components, splitting at punctuation,
underscores, and camel-case boundaries:

| Inferred rule | Matching field-name components | Examples |
| ------------- | ------------------------------ | -------- |
| `email_composite` | `email` or `mail` | `email_t`, `primaryEmail`, `mail_address_s` |
| `us_phone_composite` | `phone`, `mobile`, `telephone`, or `tel` | `phone_t`, `mobileNumber`, `home_tel_s` |
| `ssn_composite` | `ssn`, or both `social` and `security` | `ssn_t`, `customerSSN`, `social_security_number_s` |

Matching uses whole components, so `microphone_s` does not trigger
`us_phone_composite`. Schema suffixes such as `_s` and `_t` do not affect the
match. Generated reports label name-based selections as inferred.

## License and Copyright

Copyright Mark L. Bennett.

DQ uses the Apache License 2.0, which permits commercial use, modification, and incorporation into your own proprietary code, subject to its terms.
See [LICENSE.txt](LICENSE.txt) for the full license.

DQ v2 was inspired by some of the code in the original Java Data Quality
project. The original project is also
licensed under Apache 2.0: [https://github.com/lucidworks/data-quality](https://github.com/lucidworks/data-quality).
See also Mark Bennett's fork: [https://github.com/ttennebkram/data-quality](https://github.com/ttennebkram/data-quality).

## More Help

### Community

For questions, ideas, and usage help, visit the **discussion board (GitHub Discussions)**:
[https://github.com/ttennebkram/dq/discussions](https://github.com/ttennebkram/dq/discussions).

For the code and bug reports, see the project repository:
[https://github.com/ttennebkram/dq](https://github.com/ttennebkram/dq).

### Author and Consulting

I do software consulting for AI and search engine technology. I'm happy to chat!

For hands-on help, I offer an intro package of up to one hour of remote assistance for $100.
Larger tasks should be discussed separately.
You can reach me at [mbennett@ideaeng.com](mailto:mbennett@ideaeng.com?subject=Data%20Quality%20Inquiry).
