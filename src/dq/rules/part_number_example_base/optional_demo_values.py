"""Correct and deliberately invalid values for Part Numbers in part_number_example_base.

This file is an optional rule capability.  It must be present in the rule package in order to be included in the dq_demo collection/index

This file generates both valid and invalid examples of what this rule checks for.
This will be called when we generate dq_demo

The valid format for this example is three letters, a dash, and six digits,
such as ``ABC-000007``.

This module creates several types of invalid data, that fail for different reasons
"""


def suggested_field_name():
    """Suggest the field name to use for this rule's ``dq_demo`` values.

    End the field with ``_t`` for analyzed text or ``_s`` for an exact
    string/keyword. The loaders map those suffixes with dynamic fields/templates.
    """
    return 'part_number_s'


def generate_valid_value(index, rng):
    """Return a correct synthetic part number for a document index.

    ``index`` is the generated document's one-based sequence number.  The
    correct format is three letters, one dash, and six digits.  For example,
    document ``demo-000007`` passes ``index=7`` and receives ``ABC-000007``.

    ``index % 1000000`` keeps the numeric portion within six digits, and
    ``{0:06d}`` pads smaller numbers with leading zeroes.  Therefore, index 7
    becomes ``000007``.  Values repeat after one million documents because the
    part number is test data rather than a unique identifier.  ``rng`` is the
    shared seeded random generator; this valid format does not currently need it.
    """
    return 'ABC-{0:06d}'.format(index % 1000000)


def generate_invalid_value(index, rng):
    """Return one invalid part number selected by the shared seeded generator.

    ``index`` is the generated document's one-based sequence number.  For
    example, document ``demo-000007`` passes ``index=7``.  The number makes the
    bad values vary between documents instead of repeating one fixed string.

    If an invalid format needs to modify the corresponding correct value, it
    can call ``generate_valid_value(index, rng)`` directly. These examples construct
    each failure from ``index`` instead.

    ``rng`` is the shared ``random.Random`` instance created from the run's
    seed.  Calling ``rng.choice()`` selects one entry from the tuple below.
    Keeping one random generator for the run means the same seed and
    command-line options reproduce the same output.

    The modulo operator (``%``) limits a number to the required width.  For
    example, ``1234567 % 1000000`` is ``234567``.  Formatting with
    ``{0:06d}`` then renders a decimal integer at least six characters wide,
    padding smaller numbers with leading zeroes: index 7 becomes ``000007``.
    The five-digit example uses ``{0:05d}`` and modulo 100000 for the same
    reason.  Values repeat after one million documents, which is acceptable
    because these strings are test defects rather than unique identifiers.

    """
    six_digit_number = index % 1000000
    five_digit_number = index % 100000  # intentionally incorrect

    # CORRECT FORMAT: ABC-000007 (three letters, one dash, six digits).
    # Every value below intentionally violates that format in a different way.
    # A variety of failure patterns.
    values = (
        # Missing dash; example for index 7: ABC000007.
        'ABC{0:06d}'.format(six_digit_number),

        # Digit in the three-letter prefix; example: A1C-000007.
        'A1C-{0:06d}'.format(six_digit_number),

        # Only five digits; example: ABC-00007.
        'ABC-{0:05d}'.format(five_digit_number),

        # Unexpected suffix; example: ABC-000007-X.
        'ABC-{0:06d}-X'.format(six_digit_number),

        # Underscore instead of a dash; example: ABC_000007.
        'ABC_{0:06d}'.format(six_digit_number),

        # Four letters instead of three; example: ABCD-000007.
        'ABCD-{0:06d}'.format(six_digit_number),
    )

    # Return one of the results at random
    # Note: It's slightly inefficient to generate six values but use only one.
    # But this is so inexpensive and it makes the code easier to understand and modify.
    return rng.choice(values)
