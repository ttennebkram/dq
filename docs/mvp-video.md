# MVP Video Walkthrough

Keep the first video short. It demonstrates one complete Solr workflow and
uses the existing `dq-demo` collection. Save the local Solr URL and `dq-demo`
collection in `dq.ini` before recording.

## 1. Introduce DQ

DQ is a command-line Search Engine Data Quality Toolkit. This first version
checks stored values in Apache Solr and requires no third-party Python packages.

## 2. List the Fields

```sh
bin/dq --list_fields
```

Briefly point out the field names, Solr types, stored/indexed properties, and
document counts.

## 3. Run the Quick Checkup

```sh
bin/dq --report quick_checkup
```

Open `reports/quick_checkup.md`. Show the field-presence results and the
additional checks DQ recommends from field types and names.

## 4. Check Email Values

```sh
bin/dq --rule email --action csv --include_field email_t
```

Open `reports/email_t_email.csv`. Show its `id,reason,value` columns and a few
invalid, missing, or whitespace-only email values.

## 5. Close

Show the repository URL, `https://github.com/ttennebkram/dq`, and say that later
videos can cover full checkup, custom regex rules, additional search engines,
and larger collections.

Do not add those topics to the first video unless the recorded walkthrough is
too short.
