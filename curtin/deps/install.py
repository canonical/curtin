# This file is part of curtin. See LICENSE file for copyright and license info.

"""
The intent of this module is that it can be called to install deps
  python -m curtin.deps.install [-v]
"""

import argparse
import sys

from . import install_deps


def main():
    parser = argparse.ArgumentParser(
        prog='curtin-install-deps',
        description='install dependencies for curtin.')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        dest='verbosity')
    parser.add_argument('--dry-run', action='store_true', default=False)
    parser.add_argument('--no-allow-daemons', action='store_false',
                        default=True)
    args = parser.parse_args(sys.argv[1:])

    ret = install_deps(verbosity=args.verbosity, dry_run=args.dry_run,
                       allow_daemons=True)
    sys.exit(ret)


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab syntax=python
