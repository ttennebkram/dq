"""Shared defect allocation for synthetic test data."""

MISSING = object()


def _common_plan(null_count, blank_count, whitespace_count):
    blank = ('empty', 'whitespace_only')
    surrounding = ('leading_whitespace', 'trailing_whitespace',
                   'surrounding_whitespace')
    plan = ['null'] * null_count
    plan.extend(blank[index % len(blank)] for index in range(blank_count))
    plan.extend(surrounding[index % len(surrounding)]
                for index in range(whitespace_count))
    return plan

def defect_plan(count):
    """Allocate format-rule defects in a 3:3:3:11 ratio."""
    common_count = int(count * 3.0 / 20.0 + 0.5)
    plan = _common_plan(common_count, common_count, common_count)
    plan.extend(['rule'] * (count - len(plan)))
    return plan


def standard_text_defect_plan(count):
    """Keep Unicode corruption rare and distribute the rest across readable defects."""
    if count == 0:
        return []
    rule_count = max(1, int(count * 0.005 + 0.5))
    common_count = count - rule_count
    each, remainder = divmod(common_count, 3)
    counts = [each + (1 if index < remainder else 0) for index in range(3)]
    plan = _common_plan(counts[0], counts[1], counts[2])
    plan.extend(['rule'] * rule_count)
    return plan


def common_invalid_value(kind, valid_value):
    if kind == 'missing':
        return MISSING
    if kind == 'null':
        return None
    if kind == 'empty':
        return ''
    if kind == 'whitespace_only':
        return ' \t\n'
    if kind == 'leading_whitespace':
        return ' leading whitespace example'
    if kind == 'trailing_whitespace':
        return 'trailing whitespace example '
    if kind == 'surrounding_whitespace':
        return ' leading and trailing whitespace example '
    raise ValueError('not a common synthetic defect: ' + kind)
