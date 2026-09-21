"""Unicode indicators are findings for review, not proof of corruption."""
from dq.rules.procedural import failure_reason as procedural_failure_reason


def blank_reason(value):
    if value is None:
        return 'null'
    if isinstance(value, str):
        if value == '':
            return 'empty string'
        if value.isspace():
            return 'whitespace only'
    return None


def value_reasons(value, skip_null_values=False):
    """Return the first base-rule failure in standard text composite order."""
    if value is None and skip_null_values:
        return []
    if value is None:
        return ['missing_fields_base: missing or null']
    if value == '':
        return ['empty_strings_base: empty string']
    if isinstance(value, str) and value.isspace():
        return ['whitespace_only_base: whitespace-only string']
    if not isinstance(value, str):
        return []
    if value != value.strip():
        return ['surrounding_whitespace_base: leading or trailing whitespace']
    unicode_reason = procedural_failure_reason('code_points_base', value)
    return ['code_points_base: ' + unicode_reason] if unicode_reason else []
