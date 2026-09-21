"""Unicode indicators are findings for review, not proof of corruption."""
import configparser
import os
import unicodedata

from .unicode_data import block_name as _block_name, script_name as _script_name


def failure_reason(value):
    """Return one CSV failure reason, or None when the value passes."""
    examples = _bucket_examples(value)
    if len(examples) < _SUSPICIOUS_BUCKETS_THRESHOLD:
        return None
    return '{0} code-point buckets: {1}'.format(
        len(examples), ', '.join(sorted(examples)))


def _unicode_pseudotype(char, category):
    """Map General Category and special characters to a DQ pseudotype."""
    if char == '\ufffd':
        return 'replacement'
    if category == 'Cs':
        return 'surrogate'
    if category == 'Co':
        return 'private_use'
    if category == 'Cn':
        return 'unassigned'
    if category == 'Cf':
        return 'format'
    if category == 'Cc' and char not in '\t\r\n':
        return 'control'
    return 'normal'


def _bucket(char):
    """Return the Script + Block + Unicode Pseudotype bucket."""
    code_point = ord(char)
    pseudotype = _unicode_pseudotype(char, unicodedata.category(char))
    return ' / '.join((_script_name(code_point), _block_name(code_point), pseudotype))


def _bucket_examples(value):
    """Return one example character for each distinct Unicode bucket."""
    examples = {}
    for char in value:
        code_point = ord(char)
        category = unicodedata.category(char)
        name = _bucket(char)
        examples.setdefault(name, 'U+{0:04X} {1} ({2})'.format(
            code_point, unicodedata.name(char, 'UNNAMED'), category))
    return examples


def _read_threshold():
    """Read and validate this rule's suspicious-bucket threshold."""
    parser = configparser.ConfigParser(interpolation=None)
    path = os.path.join(os.path.dirname(__file__), 'rule.ini')
    with open(path, encoding='utf-8') as stream:
        parser.read_file(stream)
    value = parser.getint('base_rule', 'suspicious_buckets_threshold')
    if value < 1:
        raise ValueError(
            'suspicious_buckets_threshold found in rule.ini, must be at least 1')
    return value


_SUSPICIOUS_BUCKETS_THRESHOLD = _read_threshold()
