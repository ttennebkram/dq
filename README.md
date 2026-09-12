DQ2
===

DQ2 is a lightweight data-quality reporting tool for Apache Solr,
Elasticsearch, and OpenSearch. The first development target is:

    http://localhost:8983/solr/my-files

DQ2 is based on the original data-quality project in the ttennebkram GitHub
fork:

    https://github.com/ttennebkram/data-quality

Status
------

The project currently contains its Python packaging and CLI foundation. The
planned checks include empty fields, term statistics, Unicode code points,
dates, document counts, ID comparison, schema comparison, configuration
comparison, ID export/deletion, Solr-to-Solr copying, CSV export, and Solr
hash/shard calculation.

Reports will be written as Markdown with links between report documents. Field
selection includes all stored fields except names that begin and end with an
underscore by default and supports shell-style include and exclude patterns.

Requirements and dependencies
-----------------------------

Required software:

* Python 3.4.10 or newer

Python 3.4.10 is the minimum because the code uses dataclasses and postponed
type annotations. The CLI tests and a live Solr report have been checked with
Python 3.4.10.9. To test with this machine's separate Python 3.4.10 installation
without changing the default interpreter:

    /Library/Frameworks/Python.framework/Versions/3.7/bin/python3 bin/dq --version
    PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.7/bin/python3 -m unittest discover -s tests

Runtime Python dependencies:

* None. The initial CLI uses only the Python standard library.

Build dependencies, installed automatically by pip when building:

* setuptools 61 or newer

Development dependencies:

* None currently.

No Java, SolrJ, Rust, Node.js, Docker, or native Python extension is required
to run the CLI. A reachable Solr, Elasticsearch, or OpenSearch server is needed
to perform a report.

Run directly from the project
-----------------------------

No package installation is needed. With Python 3.4.10 or newer available as
``python3``, run the executable launcher:

    cd /Users/mbennett/Dropbox/dev/dq
    ./bin/verify-python
    ./bin/dq --help
    ./bin/dq --version

``bin/verify-python`` checks the same ``python3`` on PATH used by ``bin/dq``.
It reports the interpreter path and version, requires Python 3.4.10 or newer,
checks HTTPS support, and verifies that this checkout's DQ CLI loads. It exits
with status 0 on success or a nonzero status on failure, with errors on stderr.
It does not install software, change your environment, or contact Solr.

To use ``dq`` from any directory, add this project's ``bin`` directory to PATH:

    export PATH="/Users/mbennett/Dropbox/dev/dq/bin:$PATH"
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

Optional development installation
------------------------

    cd /Users/mbennett/Dropbox/dev/dq
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e .

Basic usage
-----------

Run without arguments to display detailed usage and the command roadmap:

    dq

The usage synopsis shows each action separately:

    dq --report NAME [NAME ...] [options]
    dq --ids empty_fields [options]
    dq --list_fields [options]
    dq --write_config [options]
    dq --help
    dq --version

Choose one action and add shared target or field-filter options as needed.

DQ then validates the target in order: first ``main_url``, then the collection
or index. If both resolve from ``dq.ini`` or another source, it explicitly says
that no action was selected and asks for ``--report NAME``, ``--ids empty_fields``, ``--list_fields``,
or ``--write_config``. This makes a missing target distinguishable from a
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
``empty_fields.md`` in the current directory:

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
``--report``, ``--list_fields``, or ``--write_config``.

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

The project includes a template containing every currently supported setting:

    /Users/mbennett/Dropbox/dev/dq/dq.ini.template

Copy it when starting configuration for another project:

    cp /Users/mbennett/Dropbox/dev/dq/dq.ini.template dq.ini

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

Without ``--write_config``, the file named by ``--config`` must already exist.
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

Python compatibility: runtime code uses ordinary classes, os.path and str.format.
The checkout launcher requires Python 3.4.10 or newer. Run bin/verify-python
without arguments to check python3 on PATH. Packaging metadata is in setup.py.
