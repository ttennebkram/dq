"""Synthetic nonblank values rejected by email_base."""


def invalid_values(valid_value, index):
    return (
        'demo{0}.example.com'.format(index),
        'demo{0}@example'.format(index),
        'demo{0}@@example.com'.format(index),
        'demo..{0}@example.com'.format(index),
        'demo {0}@example.com'.format(index),
        'demo{0}@-example.com'.format(index),
    )
