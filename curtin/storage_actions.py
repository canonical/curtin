import attr

from curtin import config, util

_type_to_cls = {}


def define(typ):
    def wrapper(c):
        c.type = attr.ib(default=typ)
        c.id = attr.ib()
        c.__annotations__["id"] = str
        c.__annotations__["type"] = str
        c = attr.s(auto_attribs=True, kw_only=True)(c)
        _type_to_cls[typ] = c
        return c

    return wrapper


def _convert_size(s):
    if isinstance(s, str):
        return int(util.human2bytes(s))
    return s


def asobject(obj):
    cls = _type_to_cls[obj["type"]]
    return config.fromdict(cls, obj)


def size(*, default=attr.NOTHING):
    return attr.ib(converter=_convert_size, default=default)
