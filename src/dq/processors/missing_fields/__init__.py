"""Missing-field CSV metadata."""
NAME = 'missing_fields'
DESCRIPTION = 'export documents whose selected field is missing or null'
RULE_TYPE = 'base'
CSV = 'dq.processors.missing_fields.processor:prepare_csv'
