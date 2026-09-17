"""Missing-field CSV metadata."""
NAME = 'missing_fields_base'
DESCRIPTION = 'export documents whose selected field is missing or null'
RULE_TYPE = 'base'
CSV = 'dq.rules.missing_fields_base.processor:prepare_csv'
