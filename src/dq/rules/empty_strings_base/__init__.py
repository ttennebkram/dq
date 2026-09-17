"""Empty-string CSV metadata."""
NAME = 'empty_strings_base'
DESCRIPTION = 'export stored text values containing zero characters'
RULE_TYPE = 'base'
CSV = 'dq.rules.empty_strings_base.processor:prepare_csv'
