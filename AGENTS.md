# Project maintenance

When adding, removing, or changing a CLI option, alias, configuration key, default,
or precedence rule, update `dq.ini.template`, `README.md`, and CLI usage/help in
the same change. The template must show every supported INI key, including
optional commented examples, and clearly distinguish command-line-only options.
Do not document a CLI option as an INI setting unless the config loader supports it.

Keep example paths portable. Generated reports use the `report_` prefix and
must remain ignored by Git; Markdown documentation must remain trackable.

Do not commit changes without explicit user authorization.
