"""Shared loader for built-in procedural base-rule value evaluators."""
import importlib

from dq.errors import ReportError


def failure_reason(rule_name, value):
    """Return one failure reason from RULE_NAME's processor, or None."""
    module_name = 'dq.rules.{0}.processor'.format(rule_name)
    try:
        evaluator = getattr(importlib.import_module(module_name), 'failure_reason')
    except (ImportError, AttributeError) as error:
        raise ReportError(
            '{0} must define processor.py failure_reason(value): {1}'.format(
                rule_name, error)) from error
    reason = evaluator(value)
    if reason is not None and not isinstance(reason, str):
        raise ReportError(
            '{0} failure_reason(value) must return a string or None'.format(
                rule_name))
    return reason
