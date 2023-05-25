# This file is part of curtin. See LICENSE file for copyright and license info.


class MutuallyExclusiveGroup:
    def __init__(self, entries) -> None:
        self.entries = entries


def populate_one_subcmd(parser, options_dict, handler):
    for entry in options_dict:
        def add_entry_to_parser(parser, entry):
            args = entry[0]
            if not isinstance(args, (list, tuple)):
                args = (args,)
            parser.add_argument(*args, **entry[1])

        if isinstance(entry, MutuallyExclusiveGroup):
            group_parser = parser.add_mutually_exclusive_group()
            subentries = entry.entries
        else:
            group_parser = parser
            subentries = [entry]

        for subentry in subentries:
            add_entry_to_parser(group_parser, subentry)
    parser.set_defaults(func=handler)

# vi: ts=4 expandtab syntax=python
