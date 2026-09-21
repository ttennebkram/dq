"""Read settings shared by base and composite rule INI files."""
import re


def _automatic_field_types(value):
    values = tuple(item.lower() for item in re.split(r'[\s,]+', value.strip()) if item)
    unknown = set(values) - {'text'}
    if unknown:
        raise ValueError('unknown automatic_field_types value: ' +
                         ', '.join(sorted(unknown)))
    return values


def _automatic_field_name_patterns(value):
    patterns = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        components = tuple(item.strip().lower() for item in line.split('+'))
        if (not all(components) or
                any(not re.match(r'^[a-z0-9]+$', item) for item in components)):
            raise ValueError('automatic_field_name_patterns lines must contain '
                             'lowercase components joined by +: ' + line)
        patterns.append(components)
    return tuple(patterns)


def read_metadata(parser):
    """Validate and return the common [rule] metadata."""
    if not parser.has_section('rule'):
        raise ValueError('expected a [rule] section')
    values = dict(parser.items('rule'))
    unknown = set(values) - {
        'description', 'automatic_field_types',
        'automatic_field_name_patterns'}
    if unknown:
        raise ValueError('unknown [rule] setting: ' + ', '.join(sorted(unknown)))
    description = values.get('description', '').strip()
    if not description:
        raise ValueError('[rule] description is required')
    automatic_types = _automatic_field_types(
        values.get('automatic_field_types', ''))
    automatic_patterns = _automatic_field_name_patterns(
        values.get('automatic_field_name_patterns', ''))
    if automatic_patterns and not automatic_types:
        raise ValueError('automatic_field_name_patterns requires '
                         'automatic_field_types')
    return {
        'description': description,
        'automatic_field_types': automatic_types,
        'automatic_field_name_patterns': automatic_patterns,
    }
