"""Predefined composite rules and deterministic expansion to base rules."""
from collections import OrderedDict
from dq.errors import ReportError
from dq.rules import (standard_text_composite, email_composite,
                      us_phone_composite, ssn_composite,
                      part_number_example_composite)


_MODULES = (standard_text_composite, email_composite, us_phone_composite,
            ssn_composite, part_number_example_composite)
COMPOSITES = OrderedDict(
    (module.NAME, {'description': module.DESCRIPTION, 'rules': module.RULES})
    for module in _MODULES)


def expand(names, base_names):
    """Flatten nested composites, preserving order and evaluating each base once."""
    base_names = set(base_names)
    flattened = []
    seen = set()

    def visit(name, stack):
        if name in COMPOSITES:
            if name in stack:
                cycle = stack[stack.index(name):] + [name]
                raise ReportError('composite rule cycle: ' + ' -> '.join(cycle))
            for child in COMPOSITES[name]['rules']:
                visit(child, stack + [name])
            return
        if name not in base_names:
            raise ReportError('unknown rule: ' + name)
        if name not in seen:
            seen.add(name)
            flattened.append(name)

    for name in names:
        visit(name, [])
    return flattened
