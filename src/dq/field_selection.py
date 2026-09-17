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

def is_text_field(field):
    """Use the schema class, including exact strings, rather than JSON encoding."""
    type_class = str(field.get('typeClass', '')).rsplit('.', 1)[-1]
    if type_class:
        return type_class in ('TextField', 'StrField', 'SortableTextField', 'UUIDField')
    # Fallback for metadata without a schema class; custom classes stay unknown.
    name = str(field.get('type', '')).lower()
    return name in ('string', 'strings', 'text', 'uuid') or name.startswith('text_')


def is_date_field(field):
    type_class = str(field.get('typeClass', '')).rsplit('.', 1)[-1]
    if type_class:
        return type_class in ('DatePointField', 'TrieDateField', 'DateField')
    return str(field.get('type', '')).lower() in ('pdate', 'pdates', 'date', 'tdate', 'tdates')
