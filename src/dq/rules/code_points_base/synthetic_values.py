"""Synthetic nonblank values rejected by code_points_base."""


def invalid_values(valid_value, index):
    return (
        valid_value + '\ufffd\u200b\ue000',
        valid_value + '\ufffd\u2060\x01',
        valid_value + '\ufffd\ue001\x02',
        valid_value + '\u200b\ue000\x03',
        '\u202e' + valid_value + '\ufffd\ue002',
        valid_value + '\u00ad\ufffd\x04',
    )
