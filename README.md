DQ v2
-----

DQ v2 is a Search Engine Data Quality Toolkit for Apache Solr, Elasticsearch, and OpenSearch. GitHub repository: [https://github.com/ttennebkram/dq](https://github.com/ttennebkram/dq). DQ v2 is based on the original Data Quality project in the ttennebkram GitHub fork: [https://github.com/ttennebkram/data-quality](https://github.com/ttennebkram/data-quality).

Contents
--------

- [Quickstart](#quickstart)
- [Requirements and dependencies](#requirements-and-dependencies)
- [Optional development installation](#optional-development-installation)
- [Basic usage](#basic-usage)
  - [Export IDs for an empty field](#export-ids-for-an-empty-field)
- [Configuration](#configuration)
  - [Configuration wizard](#configuration-wizard)
  - [Saved field filters](#saved-field-filters)
- [Generated reports and Git](#generated-reports-and-git)
- [Report behavior](#report-behavior)
- [Supporting HTTPS](#supporting-https)
  - [Create a local self-signed Solr certificate](#create-a-local-self-signed-solr-certificate)
  - [Export the public PEM file](#export-the-public-pem-file)
  - [Reference the PEM from the DQ project](#reference-the-pem-from-the-dq-project)
  - [Install the optional Solr helper](#install-the-optional-solr-helper)
  - [Switch local Solr Basic authentication on or off](#switch-local-solr-basic-authentication-on-or-off)
- [License](#license)

Quickstart
----------

The examples use `~/dev/dq` for the project checkout (`~` is your home directory).
Substitute your own checkout location. Run with Python 3.4.10 or newer; no package
installation or third-party Python dependencies are needed:

```sh
cd ~/dev/dq
./bin/verify-python
./bin/dq --help
./bin/dq --version
./bin/dq --main_url http://localhost:8983/solr --collection my-files --write_config
./bin/dq --report empty_fields
```

For guided setup instead, run `./bin/dq --config_wizard`.

Replace the server URL and collection with your own. `--write_config` saves the
target in `dq.ini`, so later commands can omit it. If Solr requires Basic
authentication, add `username` and `password` to the INI file under its existing
`[DEFAULT]` or `[dq]` section before running the report. See
[Supporting HTTPS](#supporting-https) for certificate and authentication settings.

Open `report_empty_fields.md` in your Markdown viewer.

Other available actions:

```sh
./bin/dq --list_fields
./bin/dq --ids empty_fields --include_field file_name_s > missing-ids.txt
```

ID export requires exactly one selected stored field. Field listing and ID export
write to standard output, without creating a Markdown report.

Releases are planned to offer prebuilt binaries for users who need them. These
instructions currently assume you run `./bin/dq` directly from the checkout.

``bin/verify-python`` takes no arguments and checks the same ``python3`` on PATH
used by ``bin/dq``.
It reports the interpreter path and version, requires Python 3.4.10 or newer,
checks HTTPS support, and verifies that this checkout's DQ CLI loads. It exits
with status 0 on success or a nonzero status on failure, with errors on stderr.
It does not install software, change your environment, or contact Solr.

To use ``dq`` from any directory, add this project's ``bin`` directory to PATH:

    export PATH="$HOME/dev/dq/bin:$PATH"
    hash -r
    command -v dq
    dq --version

Add the export line to your shell startup file to retain it in new terminals
(for example, ``~/.bash_profile`` for a Bash login shell or ``~/.zshrc`` for
Zsh). For a checkout elsewhere, substitute its path. Putting it first in PATH
selects this checkout ahead of a previously installed ``dq`` command.

The launcher loads code directly from this checkout and preserves the current
working directory for config lookup and report output. It uses the ``python3``
found on PATH, including an activated virtual environment.

Requirements and dependencies
-----------------------------

Required software:

* Python 3.4.10 or newer

Dependencies: No runtime or development dependencies; DQ uses only the Python standard library.

Python 3.4.10 is the tested compatibility baseline. The code uses ordinary classes,
``os.path`` and file operations, and ``str.format()`` instead of dataclasses,
pathlib, type hints, or f-strings. It retains Python's standard ``argparse``
module, available since Python 3.2. Python 3.0/3.1 are not claimed as supported.

Optional development installation
---------------------------------

    cd ~/dev/dq
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e .

On Python 3.4, prefer ``bin/dq`` without installation. If packaging tools are
needed, compatible versions include ``pip==19.1.1``, ``setuptools==43.0.0``,
and ``wheel==0.33.6``; do not run an unrestricted pip upgrade on that interpreter.
Packaging metadata lives in ``setup.py`` so older tools can read it, while
``pyproject.toml`` supplies the build backend for modern pip.

Basic usage
-----------

Run without arguments to display detailed usage and the command roadmap:

    dq

The usage synopsis shows each action separately:

    dq --report NAME [NAME ...] [options]
    dq --ids empty_fields [options]
    dq --list_fields [options]
    dq --write_config [options]
    dq --config_wizard [options]
    dq --help
    dq --version

Choose one action and add shared target or field-filter options as needed.

DQ then validates the target in order: first ``main_url``, then the collection
or index. If both resolve from ``dq.ini`` or another source, it explicitly says
that no action was selected and asks for ``--report NAME``, ``--ids empty_fields``, ``--list_fields``,
or ``--write_config`` or ``--config_wizard``. This makes a missing target distinguishable from a
missing action.

    dq --version

Select a Markdown report by name:

    dq --report empty_fields

Both singular ``--report`` and plural ``--reports`` accept one or more names,
so related checks can eventually be generated as one linked report set:

    dq --reports empty_fields date_checker

The singular form accepts the same list:

    dq --report empty_fields date_checker

The option can also be repeated:

    dq --report empty_fields --report date_checker

The accepted report names are ``empty_fields``, ``term_stats``,
``code_points``, and ``date_checker``. ``empty_fields`` is implemented; the
other three reports are planned.

The empty-fields report examines selected stored fields and writes
``report_empty_fields.md`` in the current directory:

    dq --report empty_fields

Its ``Options Used`` section records each effective option and whether it came
from the command line, an environment variable, an explicitly named
configuration file, the default configuration file, a value embedded in
``main_url``, or a built-in default. Its summary shows the collection document
count, effective include and exclude patterns, stored fields checked, and
number of incomplete fields. Its linked ``Fields`` section lists each incomplete
field's populated-document count, missing-document count, and percentage. A
missing value means Solr did not detect that field in the document; an indexed
empty string may still count as present.

``Options Used`` and ``Fields`` use Markdown pipe tables, with spaces padding
each column so the source also lines up in a fixed-width editor such as vi.
The summary appears first, followed by options and fields.

When DQ reads a configuration file, it includes that file's path in the report
summary and the ``--list_fields`` heading. The path is labeled ``default
configuration`` or ``specified by --config``. A missing-action diagnostic
identifies the file the same way.

### Export IDs for an empty field

To export the unique keys of documents missing one stored field:

    dq --ids empty_fields --include_field file_name_s > missing-file-name.txt

This is a separate action from ``--report``. It creates no Markdown file and
accepts ``-id`` as an alias for the canonical ``--ids`` option. It
prints only one ID per line to stdout. Configuration details, progress (when
stderr is a terminal), completion counts, and errors go to stderr.
Use ``--include_field[s]`` and ``--exclude_field[s]`` with the usual simple glob
patterns. They must select exactly one stored field; otherwise DQ lists the
matching fields and exits with an error. ``--ids`` cannot be combined with
``--report``, ``--list_fields``, or ``--write_config`` or ``--config_wizard``.

DQ discovers the schema's unique key instead of assuming it is named ``id``.
It requests only that field, sorted by the unique key, using Solr ``cursorMark``
paging in batches of 1,000. Each batch is flushed to stdout, so memory does not
grow with the total result count. No matches produces empty stdout and success.
IDs containing line breaks are rejected to preserve the one-ID-per-line format.

Missing means ``exists(field)`` is false, consistent with the report's field
existence check; it is not a direct inspection of null stored values.
Cursor paging is not a snapshot: avoid indexing or deleting during an export
when you need a consistent result. Partial Solr responses and request failures
stop the export with a nonzero exit status; any output already written is
incomplete. Check the exit status before using a redirected file.

List the fields in a Solr collection:

    dq --list_fields

The command above uses the project's ``dq.ini`` file. Both target values have
named command-line options that match the configuration keys:

    dq --list_fields \
       --main_url http://localhost:8983/solr \
       --collection my-files

The hyphenated spelling is retained as an alias:

    dq --list-fields \
       --main_url http://localhost:8983/solr \
       --collection my-files

The output is sorted by field name and includes concrete fields present in the
index, each field's type, stored, indexed, doc-values, and multi-valued
properties, the number of documents containing the field, and the dynamic
schema pattern that defines it. Field discovery combines Solr's Luke and Schema
APIs. When Luke does not provide a document count for a point-number, date,
vector, or non-indexed field, DQ uses a field-presence query to obtain the
count instead of leaving the value blank.

Field filtering examples
~~~~~~~~~~~~~~~~~~~~~~~~

Field filters use simple, case-sensitive glob pattern matching, not regular
expressions. ``*`` matches any number of characters, ``?`` matches one
character, and bracket expressions such as ``[0-9]`` match one character from
a set or range.

With neither ``--include_fields`` nor ``--exclude_fields``, DQ applies the
default exclusion pattern ``_*_``. This omits Solr internal fields such as
``_version_``, ``_root_``, and ``_nest_path_``. Supplying either option replaces
that default selection rule. Both options accept shell-style patterns and can
be repeated:

    dq --list_fields --include_fields 'file_*' --include_fields content

    dq --list_fields --exclude_fields '_*' --exclude_fields '*_vector'

An explicit include can therefore select an internal field when it is needed:

    dq --list_fields --include_fields _version_

The final ``s`` is optional: ``--include_field`` and ``--exclude_field`` are
aliases for the plural forms. Hyphenated spellings are also accepted:
``--include-field``, ``--include-fields``, ``--exclude-field``, and
``--exclude-fields``.

Commands whose names begin with ``--list_`` write their results to standard
output. They do not create Markdown reports or other output files. Redirect
standard output when a saved copy is wanted:

    dq --list_fields > fields.txt

Configuration
-------------

### Configuration wizard

Run `dq --config_wizard` (alias `--config-wizard`) to walk through the standard
settings: `main_url`, collection/index, optional Basic authentication username
and password, trusted PEM certificate, and include/exclude field patterns.
It writes `dq.ini` in the current directory; use `--config FILE` to create or
update another file:

```sh
./bin/dq --config_wizard
./bin/dq --config_wizard --config targets.ini
```

The wizard uses command-line settings first, then existing values in the
destination file. It does not inherit environment variables or other discovered
config files. For a new file, the suggested URL is `http://localhost:8983/solr`.
Enter keeps a default; `-` clears an optional value. If the URL includes a
collection, the wizard explains that the separate collection setting is omitted.
Clearing the username also clears the password. Password entry is hidden and the
summary redacts it, but the saved INI contains plaintext credentials.

For each field filter list, Enter keeps the list, `-` clears it, or enter one
glob per line followed by an empty line. Patterns are simple globs, not regex;
commas and spaces within a pattern are literal. Both lists empty retain the
usual default exclusion of `_*_`. Relative certificate paths entered in the
wizard are relative to the destination INI directory and are saved as absolute
paths. The wizard validates the target and certificate locally without contacting
the server, shows a summary, and asks before writing. Answer no, press Ctrl-C,
or end input to cancel without writing. It uses the same atomic, owner-only
file writing as `--write_config` and comments out changed old target/filter values.
Choose this action separately from reports, ID export, listing, or `--write_config`.


The project includes a template containing every currently supported setting:

    ~/dev/dq/dq.ini.template

Copy it when starting configuration for another project:

    cp ~/dev/dq/dq.ini.template dq.ini

The template lists all supported INI settings: `main_url`, `collection`,
`username`, `password`, `trust_certificate`, `include_fields`, and `exclude_fields`.
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

    dq --main_url http://localhost:8983/solr/my-files \
       --collection my-files \
       --list_fields

The command above exits with an explanation. Remove either the collection from
``main_url`` or the separate ``--collection`` option.

This makes the normal command short:

    dq --list_fields

Both values can be overridden on the command line:

    dq --main_url http://localhost:8983/solr \
       --collection my-files \
       --list_fields

``--index`` is a synonym for ``--collection`` for Elasticsearch and OpenSearch
terminology:

    dq --main_url http://localhost:8983/solr \
       --index my-files \
       --list_fields

Hyphenated ``--main-url`` is accepted as an alias for ``--main_url``.

Configuration file lookup
~~~~~~~~~~~~~~~~~~~~~~~~~

Unless ``--config`` is supplied, DQ looks for the nearest ``dq.ini`` in the
current directory and then each parent directory. This allows commands run in
subdirectories to use the project's configuration. If no project file exists,
DQ looks for the user-level file:

    ~/.config/dq/config.ini

Use a specific configuration file with:

    dq --config /path/to/another.ini --list_fields

Without ``--write_config`` or ``--config_wizard``, the file named by ``--config`` must already exist.
DQ reports an error instead of silently falling back to another ``dq.ini`` or
to environment settings.

When combined with ``--write_config``, ``--config FILE`` names the file to
create or update:

    dq --main_url http://localhost:8983/solr \
       --collection my-files \
       --config /path/to/another.ini \
       --write_config

Write the currently effective target settings to ``dq.ini`` in the current
directory:

    dq --main_url http://localhost:8983/solr \
       --collection my-files \
       --write_config

This produces:

    [DEFAULT]
    main_url = http://localhost:8983/solr
    collection = my-files

If ``main_url`` already contains the collection, the file omits the separate
``collection`` key:

    dq --main_url http://localhost:8983/solr/my-files --write_config

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
5. User configuration at ``~/.config/dq/config.ini``

Command-line ``--main_url`` or ``--collection`` values may override only one
part while taking the other part from the selected configuration source.

The first live report command is:

    dq --report empty_fields \
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
`--list_fields`, and `--ids`. The ID action still requires exactly one selected
stored field.

Command-line `--include_fields` replaces the saved include list; `--exclude_fields`
replaces the saved exclude list independently. Repeat a CLI option to supply
multiple patterns. Use `--include_fields ''` or `--exclude_fields ''` to clear the
corresponding saved list for a run. When both effective lists are empty, the
usual `_*_` exclusion applies; use `--include_fields '*'` to include all names.
There are no environment variables for field filters.

`--write_config` saves the effective filters and preserves previous changed
filter values as comments. The report summary displays the effective patterns,
and Options Used identifies whether they came from CLI, INI, or defaults.

Generated reports and Git
-------------------------

Generated report filenames use the reserved `report_` prefix, for example
`report_empty_fields.md`. `.gitignore` excludes `report_*` files so reports stay
out of commits while `README.md` and documentation under `docs/` remain trackable.
Keep checked-in documentation names outside that prefix. The older
`empty_fields.md` output remains ignored for existing working directories.
Git ignore rules do not untrack files that were already committed.

Report behavior
---------------

Reports use Markdown with internal links. Field filters use simple glob patterns
and exclude names beginning and ending with an underscore by default;
`empty_fields` checks selected stored fields.

## Supporting HTTPS

DQ uses exactly the protocol specified in `main_url`. It never switches from
HTTP to HTTPS or from HTTPS to HTTP, including server redirects. A redirect
that changes protocol produces an error; there is no automatic fallback.
Same-protocol redirects remain allowed for unauthenticated requests.

HTTPS verifies the server certificate and
hostname. For certificates trusted by Python's default certificate store, no
additional option is needed. Python's store may differ from the macOS Keychain.

For a private certificate authority or a self-signed Solr certificate:

```sh
dq --report empty_fields --trust_certificate certificates/solr-ca.pem
```

`--trust-certificate` is an alias. Supply a PEM file containing the trusted CA
certificate, or the server's public certificate if self-signed. A certificate
name alone is insufficient. This adds trust without disabling hostname checks.
DQ does not need the server's private key. Client-certificate authentication
(mutual TLS) and certificate-fingerprint pinning are not implemented.

HTTP Basic authentication can be configured with `--username` and `--password`,
or saved in the INI file:

```ini
[dq]
main_url = https://localhost:8983/solr
collection = my-files
username = mark
password = replace-with-your-password
trust_certificate = certificates/solr-ca.pem
```

CLI values override the corresponding INI values. Username and password must be
supplied together. Passwords are literal, including `%` characters. Certificate
paths from INI are relative to that INI file; command-line paths are relative to
the current directory. No new authentication environment variables are used.

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

HTTPS client support does not enable HTTPS on Solr. Solr itself must be configured
with a server certificate and private key before changing its URL to `https://`.


### Create a local self-signed Solr certificate

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

### Export the public PEM file

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

### Reference the PEM from the DQ project

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

Then run `dq --report empty_fields`. DQ will use HTTPS exactly as specified;
it will not switch protocols. Trusting this PEM in DQ does not install it into
the browser's certificate store.

See the [Solr HTTPS documentation](https://solr.apache.org/guide/solr/9_10/deployment-guide/enabling-ssl.html)
for the keystore and server configuration reference.

### Install the optional Solr helper

DQ distributes `solr-auth` in [aux-bin/](aux-bin/README.md). Copy it into the
Solr installation before using it. It is a standalone helper and does not
require DQ to be installed or remain at its current path.

Recommended location: `local-scripts/` under the Solr installation. From the
DQ project directory:

```sh
mkdir -p ~/dev/solr-9.10.1/local-scripts
cp aux-bin/solr-auth ~/dev/solr-9.10.1/local-scripts/solr-auth
chmod +x ~/dev/solr-9.10.1/local-scripts/solr-auth
```

Alternatively, copy it into Solr's existing `bin/` directory:

```sh
cp aux-bin/solr-auth ~/dev/solr-9.10.1/bin/solr-auth
chmod +x ~/dev/solr-9.10.1/bin/solr-auth
```

You can also copy it directly into the Solr installation root. The helper
detects the installation from its own location in any of these three layouts.
Use `--solr_dir DIR` to specify the installation explicitly when running it
from elsewhere, including directly from DQ's `aux-bin/`.

Choose one installed location. The examples below use `local-scripts/`; use
`bin/solr-auth` or `./solr-auth` instead if you chose another location. After
updating the helper in DQ, repeat the copy to update your installed copy.
Copying the script does not change authentication or overwrite the saved login.
The password file is always `local-auth.ini` in the selected Solr installation
root, never in DQ's `aux-bin/`.

### Switch local Solr Basic authentication on or off

The development server normally runs without a login. Use the helper in the Solr installation when testing authentication:

```sh
cd ~/dev/solr-9.10.1
./local-scripts/solr-auth status
./local-scripts/solr-auth on
./local-scripts/solr-auth off
```

On the first `on`, the helper prompts for a username and password and saves them
in plaintext in `local-auth.ini` under the Solr installation, with owner-only
permissions. Later `on` commands reuse that login without prompting. `off` keeps
the saved login for next time. This is separate from the certificate keystore
password. To replace the saved login, first turn authentication off, then run:

```sh
./local-scripts/solr-auth on --set_credentials
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
./local-scripts/solr-auth on --restart
./local-scripts/solr-auth off --restart
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

License
-------

DQ uses the Apache License 2.0, which permits commercial use, modification, and incorporation into your own proprietary code, subject to its terms.
See [LICENSE.txt](LICENSE.txt) for the full license.
