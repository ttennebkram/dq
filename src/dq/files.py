"""Small file helpers using ordinary paths and file operations."""

import os
import tempfile


def absolute_path(path):
    return os.path.realpath(os.path.expanduser(str(path)))


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
