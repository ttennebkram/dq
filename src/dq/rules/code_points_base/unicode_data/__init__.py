"""Unicode 15.0 Script and Block lookup for the code-points rule."""
from bisect import bisect_right

from . import blocks, scripts


def _value(ranges, values, code_point):
    return values[bisect_right(ranges, code_point) - 1]


def script_name(code_point):
    """Return the full Unicode Script name for a code point."""
    short_name = _value(scripts.RANGES, scripts.VALUES, code_point)
    return scripts.NAMES.get(short_name, short_name)


def block_name(code_point):
    """Return the Unicode Block name for a code point."""
    return _value(blocks.RANGES, blocks.VALUES, code_point)
