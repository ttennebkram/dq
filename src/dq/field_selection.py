"""Field-name selection shared by DQ commands and report generators."""
from fnmatch import fnmatchcase
DEFAULT_EXCLUDED_FIELDS = ('_*_',)


def select_fields(fields, *, include=(), exclude=()):
    """Select fields using shell-style patterns and DQ's default exclusions."""
    effective_exclude = exclude if include or exclude else DEFAULT_EXCLUDED_FIELDS
    selected = []
    for field in fields:
        name = str(field.get('name', ''))
        if include and (not any((fnmatchcase(name, pattern) for pattern in include))):
            continue
        if any((fnmatchcase(name, pattern) for pattern in effective_exclude)):
            continue
        selected.append(dict(field))
    return selected
