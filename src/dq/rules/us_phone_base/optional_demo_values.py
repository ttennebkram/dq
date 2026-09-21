"""Correct and deliberately invalid synthetic values for us_phone_base."""


def suggested_field_name():
    """Suggest the text field created for phone examples in ``dq_demo``."""
    return 'phone_t'


def generate_valid_value(index, rng):
    """Return a correct synthetic US phone number for a document index.

    The fictional 555 exchange keeps the demo values recognizable as test
    data.  For example, document index 7 receives ``212-555-0107``.  ``rng``
    is the shared seeded random generator; this format does not currently need it.
    """
    return '212-555-{0:04d}'.format(100 + index % 100)


def generate_invalid_value(index, rng):
    """Return one invalid phone number selected by the seeded generator."""
    values = (
        '212-555-{0:03d}'.format(index % 1000),
        '112-555-{0:04d}'.format(index % 10000),
        '(212-555-{0:04d}'.format(index % 10000),
        '212/555/{0:04d}'.format(index % 10000),
        '212-155-{0:04d}'.format(index % 10000),
        '212-555-{0:05d}'.format(index % 100000),
    )
    return rng.choice(values)
