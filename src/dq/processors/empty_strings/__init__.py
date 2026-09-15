"""Empty-string CSV metadata."""
NAME = 'empty_strings'
DESCRIPTION = 'export stored text values containing zero characters'
RULE_TYPE = 'base'
CSV = 'dq.processors.empty_strings.processor:prepare_csv'
