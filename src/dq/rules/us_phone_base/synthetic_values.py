"""Synthetic nonblank values rejected by us_phone_base."""


def invalid_values(valid_value, index):
    return (
        '212-555-{0:03d}'.format(index % 1000),
        '112-555-{0:04d}'.format(index % 10000),
        '(212-555-{0:04d}'.format(index % 10000),
        '212/555/{0:04d}'.format(index % 10000),
        '212-155-{0:04d}'.format(index % 10000),
        '212-555-{0:05d}'.format(index % 100000),
    )
