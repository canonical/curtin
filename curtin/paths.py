# This file is part of curtin. See LICENSE file for copyright and license info.
import os

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)


def target_path(target, path=None):
    # return 'path' inside target, accepting target as None
    if target in (None, ""):
        target = "/"
    elif not isinstance(target, string_types):
        raise ValueError("Unexpected input for target: %s" % target)
    else:
        target = os.path.abspath(target)
        # abspath("//") returns "//" specifically for 2 slashes.
        if target.startswith("//"):
            target = target[1:]

    if not path:
        return target

    if not isinstance(path, string_types):
        raise ValueError("Unexpected input for path: %s" % path)

    # os.path.join("/etc", "/foo") returns "/foo". Chomp all leading /.
    while len(path) and path[0] == "/":
        path = path[1:]

    return os.path.join(target, path)

# vi: ts=4 expandtab syntax=python
