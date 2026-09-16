"""Predefined standard text composite rule."""
NAME = 'standard_text_composite'
DESCRIPTION = 'missing, empty, whitespace, and unusual Unicode checks'
RULE_TYPE = 'composite'
RULES = ('missing_fields_base', 'empty_strings_base', 'whitespace_only_base',
         'surrounding_whitespace_base', 'code_points_base')
