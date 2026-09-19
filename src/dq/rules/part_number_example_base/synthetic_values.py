"""Correct and deliberately invalid values for part_number_example_base.

The valid example format is three letters, a dash, and six digits, such as
``PRT-000007``.  This module deliberately changes one part of that format at a
time so generated demo data contains several understandable failure cases.
"""


def valid_value(index):
    """Return a correct synthetic part number for a document index.

    ``index`` is the generated document's one-based sequence number.  The
    correct format is three letters, one dash, and six digits.  For example,
    document ``demo-000007`` passes ``index=7`` and receives ``PRT-000007``.

    ``index % 1000000`` keeps the numeric portion within six digits, and
    ``{0:06d}`` pads smaller numbers with leading zeroes.  Therefore, index 7
    becomes ``000007``.  Values repeat after one million documents because the
    part number is test data rather than a unique identifier.
    """
    return 'PRT-{0:06d}'.format(index % 1000000)


def invalid_value_count():
    """Return the number of invalid part-number formats available below."""
    return 6


def invalid_value(valid_value, index, choice):
    """Return one invalid part number selected by the caller's seeded choice.

    ``index`` is the generated document's one-based sequence number.  For
    example, document ``demo-000007`` passes ``index=7``.  The number makes the
    bad values vary between documents instead of repeating one fixed string.

    ``valid_value`` is the original valid field value that will be replaced.
    Every synthetic-value generator receives it through the shared generator
    interface.  These part-number examples do not need to inspect it because
    they construct each failure from ``index``.

    ``choice`` is a random integer supplied by the shared, seeded demo-data
    generator.  This module uses modulo to select one entry from the tuple
    below.  Keeping randomness in the shared generator means the same seed and
    command-line options reproduce the same output.

    The modulo operator (``%``) limits a number to the required width.  For
    example, ``1234567 % 1000000`` is ``234567``.  Formatting with
    ``{0:06d}`` then renders a decimal integer at least six characters wide,
    padding smaller numbers with leading zeroes: index 7 becomes ``000007``.
    The five-digit example uses ``{0:05d}`` and modulo 100000 for the same
    reason.  Values repeat after one million documents, which is acceptable
    because these strings are test defects rather than unique identifiers.

    With ``index=7``, the possible examples are:

    * ``PRT000007``: missing dash
    * ``P1T-000007``: digit where a letter is required
    * ``PRT-00007``: only five digits
    * ``PRT-000007-X``: unexpected suffix
    * ``PRT_000007``: underscore instead of a dash
    * ``PART-000007``: four letters instead of three
    """
    six_digit_number = index % 1000000
    five_digit_number = index % 100000

    # CORRECT FORMAT: PRT-000007 (three letters, one dash, six digits).
    # Every value below intentionally violates that format in a different way.
    values = (
        'PRT{0:06d}'.format(six_digit_number),
        'P1T-{0:06d}'.format(six_digit_number),
        'PRT-{0:05d}'.format(five_digit_number),
        'PRT-{0:06d}-X'.format(six_digit_number),
        'PRT_{0:06d}'.format(six_digit_number),
        'PART-{0:06d}'.format(six_digit_number),
    )
    return values[choice % len(values)]
