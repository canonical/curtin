# This file is part of curtin. See LICENSE file for copyright and license info.

"""
The intent point of this module is that it can be called
and exit success or fail, indicating that deps should be there.
  python -m curtin.deps.check [-v]
"""
import argparse
import sys

from . import find_missing_deps


def debug(level, msg_level, msg):
    if level >= msg_level:
        if msg[-1] != "\n":
            msg += "\n"
        sys.stderr.write(msg)


def main():
    parser = argparse.ArgumentParser(
        prog='curtin-check-deps',
        description='check dependencies for curtin.')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        dest='verbosity')
    args, extra = parser.parse_known_args(sys.argv[1:])

    errors = find_missing_deps()

    if len(errors) == 0:
        # exit 0 means all dependencies are available.
        debug(args.verbosity, 1, "No missing dependencies")
        sys.exit(0)

    missing_pkgs = []
    fatal = []
    for e in errors:
        if e.fatal:
            fatal.append(e)
        debug(args.verbosity, 2, str(e))
        missing_pkgs += e.deps

    if len(fatal):
        for e in fatal:
            debug(args.verbosity, 1, str(e))
        sys.exit(1)

    debug(args.verbosity, 1,
          "Fix with:\n  apt-get -qy install %s\n" %
          ' '.join(sorted(missing_pkgs)))

    # we exit higher with less deps needed.
    # exiting 99 means just 1 dep needed.
    sys.exit(100-len(missing_pkgs))


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab syntax=python
