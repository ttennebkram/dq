"""Synthetic nonblank values rejected by part_number_example_base."""


def invalid_values(valid_value, index):
    return (
        'PRT{0:06d}'.format(index % 1000000),
        'P1T-{0:06d}'.format(index % 1000000),
        'PRT-{0:05d}'.format(index % 100000),
        'PRT-{0:06d}-X'.format(index % 1000000),
        'PRT_{0:06d}'.format(index % 1000000),
        'PART-{0:06d}'.format(index % 1000000),
    )
