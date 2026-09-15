Reports

Run DQ from the main project directory, for example:

    bin/dq --report quick_checkup

Open reports/quick_checkup.md to see the results. Generated Markdown reports,
CSV exports, and supporting SVG graphs are ignored by Git; this README is
retained. Use --reports_dir DIR or reports_dir in dq.ini to change the output
directory for both Markdown and CSV.

Rule exports use FIELD_NAME_RULE.csv. For example:

    bin/dq --rule email --action csv --include_field email_t

writes reports/email_t_email.csv. Field names retain ASCII letters, digits,
dashes, and underscores; every other character becomes an underscore.

Special reports provide summaries, field details, and next steps. They are not generic
Markdown copies of CSV. Quick checkup writes one summary table of fields and
document counts and no CSVs. Full checkup adds field-detail Markdown and
FIELD_NAME_full_checkup.csv files with all stored-value findings.
Presence-only fields have counts but no CSV. CSV links appear in the report.
CSV means comma-separated values: document ID, rule/reason, and field value.
If multiple rules apply to one value, the first failure in the rule chain is
reported. Single-valued fields have at most one row per document; multivalued
fields can have one per failing value.

Report runs list Main Report File (or Files), followed by Other Created Files
when present. CSV runs use Files created. All paths are relative to the
working directory, such as reports/email_t_email.csv. DQ creates missing directories automatically
and announces when it creates them. A later run replaces the same filename.

Successful scans append timings to processing-stats.jsonl in this directory.
This local history records the target, fields, rule/report, counts, elapsed time,
and processing rate, without document values or credentials. It is ignored by Git.
Quick checkup performs no scan and adds no timing entry. A user-reported rate is
labeled separately when the full run details are unknown.

This guide uses a .txt extension so that running rm *.md from the reports
directory removes Markdown reports without deleting this README.
