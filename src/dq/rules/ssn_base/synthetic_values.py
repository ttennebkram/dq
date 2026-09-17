"""Synthetic nonblank values rejected by ssn_base."""


def invalid_values(valid_value, index):
    return (
        '000-12-{0:04d}'.format(index % 10000),
        '666-12-{0:04d}'.format(index % 10000),
        '900-12-{0:04d}'.format(index % 10000),
        '123-00-{0:04d}'.format(index % 10000),
        '123-45-0000',
        '123-45{0:04d}'.format(index % 10000),
    )
