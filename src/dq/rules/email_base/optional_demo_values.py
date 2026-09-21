"""Correct and deliberately invalid synthetic values for email_base."""


def suggested_field_name():
    """Suggest the text field created for email examples in ``dq_demo``."""
    return 'email_t'


def generate_valid_value(index, rng):
    """Return a correct synthetic email for a one-based document index.

    For example, document index 7 receives ``demo7@example.com``.  ``rng`` is
    the shared seeded random generator; this format does not currently need it.
    """
    return 'demo{0}@example.com'.format(index)


def generate_invalid_value(index, rng):
    """Return one invalid email selected by the shared seeded generator."""
    values = (
        'demo{0}.example.com'.format(index),
        'demo{0}@example'.format(index),
        'demo{0}@@example.com'.format(index),
        'demo..{0}@example.com'.format(index),
        'demo {0}@example.com'.format(index),
        'demo{0}@-example.com'.format(index),
    )
    return rng.choice(values)
