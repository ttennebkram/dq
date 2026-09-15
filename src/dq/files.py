"""Small file helpers using ordinary paths and file operations."""

import os
import re
import tempfile


def absolute_path(path):
    return os.path.realpath(os.path.expanduser(str(path)))


def display_path(path):
    """Show paths relative to the working directory when the OS permits it."""
    try:
        return os.path.relpath(os.path.realpath(path), os.path.realpath(os.getcwd()))
    except ValueError:  # Windows cannot make paths relative across drives.
        return os.path.abspath(path)


def print_generated_files(paths, main_reports=None, updated_paths=None, path_details=None):
    """Separate report entry points from supporting files; keep CSV runs simple."""
    paths = list(paths)
    path_details = path_details or {}
    def displayed(path):
        detail = path_details.get(absolute_path(path))
        return display_path(path) + (' ({0})'.format(detail) if detail else '')
    if main_reports is None:
        groups = [('Files created', paths)]
    else:
        primary = set(absolute_path(path) for path in main_reports)
        main = [path for path in paths if absolute_path(path) in primary]
        other = [path for path in paths if absolute_path(path) not in primary]
        groups = [('Main Report File' if len(main) == 1 else 'Main Report Files', main),
                  ('Other Created Files', other)]
    for heading, group in groups:
        if group:
            print('\n' + heading + ':')
            for path in group:
                print('  ' + displayed(path))
    if updated_paths:
        print('\nFiles updated:')
        for path in updated_paths:
            print('  ' + displayed(path))


def field_filename(field_name, rule_name, extension):
    """Replace each character outside ASCII letters/digits, dash and underscore."""
    field_name = re.sub(r'[^A-Za-z0-9_-]', '_', field_name)
    return '{0}_{1}.{2}'.format(field_name, rule_name, extension)


def field_output_paths(directory, rule_name, fields, extension):
    """Plan per-field files before scanning or overwriting any outputs."""
    from collections import OrderedDict
    from dq.processors import ReportError
    paths = OrderedDict()
    used = {}
    for field in fields:
        name = field if isinstance(field, str) else field['name']
        filename = field_filename(name, rule_name, extension)
        # Also protect the usual case-insensitive macOS/Windows filesystems.
        key = filename.lower()
        if key in used:
            raise ReportError('field filenames collide: {0!r} and {1!r}; select them separately and use different reports_dir directories'.format(used[key], name))
        used[key] = name
        paths[name] = os.path.join(directory, filename)
    if not paths:
        raise ReportError('no fields selected for output')
    return paths


def field_option_details(details, path, field):
    result = [(key, str(path) if key == 'output file' else value,
               'field name and report name within reports_dir' if key == 'output file' else source)
              for key, value, source in details]
    result.append(('field', field, 'field represented by this report'))
    return result


def create_directory(path):
    """Create missing directories; return True only when this call creates them."""
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise
        return False
    return True


def write_text(path, contents):
    """Replace a UTF-8 file atomically, cleaning up a failed temporary write."""
    path = str(path)
    parent = os.path.dirname(path) or '.'
    if not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError:
            if not os.path.isdir(parent):
                raise
    descriptor, temporary = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', dir=parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(contents)
        os.replace(temporary, path)
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
