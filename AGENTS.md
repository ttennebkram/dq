# Project maintenance

When adding, removing, or changing a CLI option, alias, configuration key, default,
or precedence rule, update `dq.ini.template`, `README.md`, and CLI usage/help in
the same change. The template must show every supported INI key, including
optional commented examples, and clearly distinguish command-line-only options.
Do not document a CLI option as an INI setting unless the config loader supports it.

Keep example paths portable. Rule exports use `<FIELD_NAME>_<RULE_NAME>.csv`; special reports choose their Markdown layout;
quick checkup writes only `quick_checkup.md`; full checkup writes a
`full_checkup.md` overview with field details and CSV findings. Sanitize
field names to ASCII letters, digits, dashes, and underscores. Output goes in
the configured reports directory (default: `reports/`). Generated output must remain ignored by Git; project documentation,
including `reports/README.txt`, must remain trackable.

Do not commit changes without explicit user authorization.

Use title case for README section headings, preserving command names and acronyms.
Keep the table of contents labels and order synchronized with the sections.

Organize the main README with usage scenarios first, then developer sections,
then licensing, copyright, and community/author information. Keep the detailed
HTTPS and self-signed certificate walkthrough near the end of the usage sections.

Keep the README Rules and Actions reference synchronized with the processor
registry and CLI, including CSV availability and planned reports.

Place the FAQ immediately before License and Copyright in the main README.

Use rule for the condition that selects records and action for what DQ does
with those records (report, CSV, or a future collection/index update). A rule
may test a regex match or nonmatch, nulls, whitespace, or other conditions.
Use command for setup, listing, and help utilities. A regex pattern remains the
expression stored in a .regex file; a processor is an internal implementation.

Defer full test-suite runs during active edits and design discussion. Batch them
when there is no other requested work pending; do not run every test after each
small change. Use focused checks only when needed for the immediate change.

Ordinary rules export CSV; do not add generic per-rule Markdown reports.
Special reports coordinate checks and provide analysis, charts, and next steps.
Quick checkup writes a single Markdown summary without CSVs. Full checkup automatically
exports per-field CSV findings from its shared stored-value scan. Use --rule NAME --action csv
for findings and --report NAME for special reports (--action report is implied).
Do not add a `--csv` shorthand.

Date analysis and graphs are deferred beyond the MVP. Native date fields receive
only presence checks in automatic checkups, even with value-check overrides.

CSV records contain only the first failed check for each value, in check order.
Single-valued fields have at most one row per document; multivalued fields may
have one row per failing value. Full-checkup counts and CSVs use the same rule.
