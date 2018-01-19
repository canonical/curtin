# This file is part of curtin. See LICENSE file for copyright and license info.


def populate_one_subcmd(parser, options_dict, handler):
    for ent in options_dict:
        args = ent[0]
        if not isinstance(args, (list, tuple)):
            args = (args,)
        parser.add_argument(*args, **ent[1])
    parser.set_defaults(func=handler)

# vi: ts=4 expandtab syntax=python
