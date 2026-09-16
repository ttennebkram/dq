"""Predefined US SSN composite rule."""
NAME = 'ssn_composite'
DESCRIPTION = 'standard text checks followed by US SSN syntax'
RULE_TYPE = 'composite'
RULES = ('standard_text_composite', 'ssn_base')
