"""Predefined US phone composite rule."""
NAME = 'us_phone_composite'
DESCRIPTION = 'standard text checks followed by US phone syntax'
RULE_TYPE = 'composite'
RULES = ('standard_text_composite', 'us_phone_base')
