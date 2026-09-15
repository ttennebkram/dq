"""Whitespace-only CSV metadata."""
NAME = 'whitespace_only'
DESCRIPTION = 'export nonempty stored strings containing only whitespace'
RULE_TYPE = 'base'
CSV = 'dq.processors.whitespace_only.processor:prepare_csv'
