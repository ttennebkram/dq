# DQ Rules Package

This directory contains DQ's base rules, predefined composite rules, and the
shared code that discovers and runs them. Rule names come from directory names.
A base-rule directory ends in `_base`; a predefined composite-rule directory
ends in `_composite`. Directory and file names without a `_base` or `_composite`
suffix are supporting files for the overall rules package.

## Shared Files and Directories

These entries do not define public rules ending in `_base` or `_composite`.

| Entry | Purpose |
| ----- | ------- |
| `README.md` | This package guide. |
| `__init__.py` | Marks `dq.rules` as a Python package. |
| `chain.py` | Runs an ordered list of flattened base rules during one stored-value scan and reports the first failure for each value. |
| `composites.py` | Discovers `[composite_rule]` definitions and recursively flattens nested composites into ordered base rules. |
| `metadata.py` | Validates the common `[rule]` section shared by base and composite rules, including automatic matching declarations. |
| `procedural.py` | Loads a procedural rule's `processor.py` and calls its public `failure_reason(value)` function. |
| `synthetic_values.py` | Shared support for generating valid and deliberately invalid values for the `dq_demo` collection/index. |
| `text/` | Shared text-check helpers used by checkup processing. It is infrastructure, not a public rule. |
| `text/__init__.py` | Marks the shared text-helper directory as a Python package. |
| `text/processor.py` | Applies the standard text checks in their defined order for checkup processing. |
| `regex/` | Shared discovery, compilation, and evaluation code for regex-based base rules. It is infrastructure, not a public rule. |
| `regex/__init__.py` | Marks the shared regex directory as a Python package. |
| `regex/definitions.py` | Finds regex-based rule INIs, validates their settings, reads `.regex` files, and compiles their expressions. |
| `regex/engine.py` | Shared direct regex-rule evaluator and CSV handler. Composite and multi-rule runs use `chain.py`. |
| `__pycache__/` | Generated Python bytecode cache. It is ignored by Git and is not source code. |

## Rule Directory Patterns

| Entry Pattern | Purpose |
| ------------- | ------- |
| `<RULE_NAME>_base/` | One base rule. Its `rule.ini` must contain `[rule]` and `[base_rule]`, but not `[composite_rule]`. |
| `<RULE_NAME>_composite/` | One predefined composite rule. Its `rule.ini` must contain `[rule]` and `[composite_rule]`, but not `[base_rule]`. |
| `<RULE_NAME>_base/rule.ini` | Common metadata under `[rule]` and base-specific settings under `[base_rule]`. One or more `[regex:regexNN]` sections make it a regex-based rule. |
| `<RULE_NAME>_base/processor.py` | Procedural evaluator when the rule cannot be expressed as regex configuration. Its public interface is `failure_reason(value)`, returning one reason string for failure or `None` for success. |
| `<RULE_NAME>_base/*.regex` | One or more extended regular expressions referenced by numbered sections in `rule.ini`. |
| `<RULE_NAME>_base/optional_demo_values.py` | Optional hooks for generating representative `dq_demo` values for that rule. |
| `<RULE_NAME>_base/README.md` | Optional detailed documentation for a rule whose behavior needs more explanation. |
| `<RULE_NAME>_composite/rule.ini` | Common metadata under `[rule]` and an ordered component list under `[composite_rule]`. Components may be base rules or other composites. |
| `<RULE_NAME>_base/__init__.py` or `<RULE_NAME>_composite/__init__.py` | Marks the rule directory as a Python package. Rule names and types are derived from the directory and `rule.ini`, not this file. |

## Regex-Based Rules

A regex-based rule is a `_base` directory whose `rule.ini` contains `[rule]`,
`[base_rule]`, and at least one numbered section such as `[regex:regex01]`.
Each numbered section references a separate `.regex` file. The shared
`regex/definitions.py` code loads and compiles those expressions; the shared
rule chain evaluates them. A regex-based rule does not need `processor.py`.

A procedural base rule has no `[regex:regexNN]` section and supplies
`processor.py`. The small built-in missing/empty/whitespace checks are currently
implemented directly in `chain.py`; moving each one behind the same procedural
interface would make that contract fully uniform.

## Automatic Rule Selection

A base or composite rule can opt into automatic checkup selection in its common
`[rule]` section:

```ini
[rule]
description = standard text checks followed by US phone syntax
automatic_field_types = text
automatic_field_name_patterns =
    phone
    mobile

[composite_rule]
rules =
    standard_text_composite
    us_phone_base
```

Each pattern line is an alternative. A `+` joins components that must all be
present, as in `social + security`. DQ splits field names at punctuation,
underscores, and camel-case boundaries and compares complete components without
case sensitivity. Thus `phone_t` matches `phone`, while `microphone_text` does
not. A rule with `automatic_field_types = text` and no name patterns is a
fallback for text/string fields when no more specific pattern matches.
If multiple specialized rules match one field, DQ selects the first rule name
alphabetically. Quick checkup lists the selected rule and the other matches;
full checkup uses that same selection.

## Current Rules

| Rule | Type | Implementation or Components |
| ---- | ---- | ---------------------------- |
| `code_points_base` | Base | Procedural Unicode Script, Block, and Pseudotype bucket check. |
| `email_base` | Base | Regex-based email-address syntax check. |
| `empty_strings_base` | Base | Reports stored strings containing zero characters. |
| `missing_fields_base` | Base | Reports documents whose selected field is missing or null. |
| `part_number_example_base` | Base | Example regex rule for three letters, a dash, and six digits. |
| `ssn_base` | Base | Regex-based US Social Security-number syntax check. |
| `surrounding_whitespace_base` | Base | Reports strings with leading or trailing whitespace. |
| `us_phone_base` | Base | Regex-based US phone-number syntax check. |
| `whitespace_only_base` | Base | Reports nonempty strings containing only whitespace. |
| `standard_text_composite` | Predefined composite | `missing_fields_base`, `empty_strings_base`, `whitespace_only_base`, `surrounding_whitespace_base`, and `code_points_base`. |
| `email_composite` | Predefined composite | `standard_text_composite`, then `email_base`. |
| `part_number_example_composite` | Predefined composite | `standard_text_composite`, then `part_number_example_base`. |
| `ssn_composite` | Predefined composite | `standard_text_composite`, then `ssn_base`. |
| `us_phone_composite` | Predefined composite | `standard_text_composite`, then `us_phone_base`. |

Run `bin/dq --list_rules` from the project directory for the catalog produced
from the current rule directories and INI descriptions.
