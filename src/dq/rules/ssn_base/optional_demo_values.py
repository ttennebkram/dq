"""Correct and deliberately invalid synthetic values for ssn_base."""


def suggested_field_name():
    """Suggest the text field created for SSN examples in ``dq_demo``."""
    return 'ssn_t'


def generate_valid_value(index, rng):
    """Return a correctly formatted synthetic SSN-shaped value.

    This validates only the ``NNN-NN-NNNN`` shape used by the demo rule; it is
    fictional test data.  For example, index 7 produces ``123-45-1007``.
    ``rng`` is shared and seeded; this format does not currently need it.
    """
    return '123-45-{0:04d}'.format(1000 + index % 9000)


def generate_invalid_value(index, rng):
    """Return one invalid SSN-shaped value selected by the seeded generator."""
    values = (
        '000-12-{0:04d}'.format(index % 10000),
        '666-12-{0:04d}'.format(index % 10000),
        '900-12-{0:04d}'.format(index % 10000),
        '123-00-{0:04d}'.format(index % 10000),
        '123-45-0000',
        '123-45{0:04d}'.format(index % 10000),
    )
    return rng.choice(values)
