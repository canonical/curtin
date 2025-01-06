# This file is part of curtin. See LICENSE file for copyright and license info.

import json
import typing

import attr
import yaml

ARCHIVE_HEADER = "#curtin-config-archive"
ARCHIVE_TYPE = "text/curtin-config-archive"
CONFIG_HEADER = "#curtin-config"
CONFIG_TYPE = "text/curtin-config"

try:
    # python2
    _STRING_TYPES = (str, basestring, unicode)
except NameError:
    # python3
    _STRING_TYPES = (str,)


def merge_config_fp(cfgin, fp):
    merge_config_str(cfgin, fp.read())


def merge_config_str(cfgin, cfgstr):
    cfg2 = yaml.safe_load(cfgstr)
    if not isinstance(cfg2, dict):
        raise TypeError("Failed reading config. not a dictionary: %s" % cfgstr)

    merge_config(cfgin, cfg2)


def merge_config(cfg, cfg2):
    # update cfg by merging cfg2 over the top
    for k, v in cfg2.items():
        if isinstance(v, dict) and isinstance(cfg.get(k, None), dict):
            merge_config(cfg[k], v)
        else:
            cfg[k] = v


def merge_cmdarg(cfg, cmdarg, delim="/"):
    merge_config(cfg, cmdarg2cfg(cmdarg, delim))


def cmdarg2cfg(cmdarg, delim="/"):
    if '=' not in cmdarg:
        raise ValueError('no "=" in "%s"' % cmdarg)

    key, val = cmdarg.split("=", 1)
    cfg = {}
    cur = cfg

    is_json = False
    if key.startswith("json:"):
        is_json = True
        key = key[5:]

    items = key.split(delim)
    for item in items[:-1]:
        cur[item] = {}
        cur = cur[item]

    if is_json:
        try:
            val = json.loads(val)
        except (ValueError, TypeError):
            raise ValueError("setting of key '%s' had invalid json: %s" %
                             (key, val))

    # this would occur if 'json:={"topkey": "topval"}'
    if items[-1] == "":
        cfg = val
    else:
        cur[items[-1]] = val

    return cfg


def load_config_archive(content):
    archive = yaml.safe_load(content)
    config = {}
    for part in archive:
        if isinstance(part, (str,)):
            if part.startswith(ARCHIVE_HEADER):
                merge_config(config, load_config_archive(part))
            elif part.startswith(CONFIG_HEADER):
                merge_config_str(config, part)
        elif isinstance(part, dict) and isinstance(part.get('content'), str):
            payload = part.get('content')
            if (part.get('type') == ARCHIVE_TYPE or
                    payload.startswith(ARCHIVE_HEADER)):
                merge_config(config, load_config_archive(payload))
            elif (part.get('type') == CONFIG_TYPE or
                  payload.startswith(CONFIG_HEADER)):
                merge_config_str(config, payload)
    return config


def load_config(cfg_file):
    with open(cfg_file, "r") as fp:
        content = fp.read()
    if not content.startswith(ARCHIVE_HEADER):
        return yaml.safe_load(content)
    else:
        return load_config_archive(content)


def load_command_config(args, state):
    if hasattr(args, 'config') and args.config:
        return args.config
    else:
        # state 'config' points to a file with fully rendered config
        cfg_file = state.get('config')

    if not cfg_file:
        cfg = {}
    else:
        cfg = load_config(cfg_file)
    return cfg


def dump_config(config):
    return yaml.dump(config, default_flow_style=False, indent=2)


def value_as_boolean(value):
    false_values = (False, None, 0, '0', 'False', 'false', 'None', 'none', '')
    return value not in false_values


def _convert_install_devices(value):
    if isinstance(value, str):
        return [value]
    return value


@attr.s(auto_attribs=True)
class BootCfg:
    install_devices_default = object()
    install_devices: typing.Optional[typing.List[str]] = attr.ib(
        converter=_convert_install_devices, default=install_devices_default)
    probe_additional_os: bool = attr.ib(
        default=False, converter=value_as_boolean)
    remove_duplicate_entries: bool = True
    remove_old_uefi_loaders: bool = True
    reorder_uefi: bool = True
    reorder_uefi_force_fallback: bool = attr.ib(
        default=False, converter=value_as_boolean)
    replace_linux_default: bool = attr.ib(
        default=True, converter=value_as_boolean)
    terminal: str = "console"
    update_nvram: bool = attr.ib(default=True, converter=value_as_boolean)


@attr.s(auto_attribs=True)
class KernelConfig:
    package: typing.Optional[str] = None
    fallback_package: str = "linux-generic"
    mapping: dict = attr.Factory(dict)
    install: bool = attr.ib(default=True, converter=value_as_boolean)
    remove: typing.Union[list, str, None] = None

    def remove_needed(self) -> bool:
        to_remove = self.kernels_to_remove()
        if bool(to_remove):
            return bool(to_remove)
        return self.remove == "existing"

    def kernels_to_remove(self) -> typing.Optional[list]:
        if isinstance(self.remove, list):
            return self.remove
        return None


class SerializationError(Exception):
    def __init__(self, obj, path, message):
        self.obj = obj
        self.path = path
        self.message = message

    def __str__(self):
        p = self.path
        if not p:
            p = 'top-level'
        return f"processing {self.obj}: at {p}, {self.message}"


@attr.s(auto_attribs=True)
class SerializationContext:
    obj: typing.Any
    cur: typing.Any
    path: str
    metadata: typing.Optional[typing.Dict]

    @classmethod
    def new(cls, obj):
        return SerializationContext(obj, obj, '', {})

    def child(self, path, cur, metadata=None):
        if metadata is None:
            metadata = self.metadata
        return attr.evolve(
            self, path=self.path + path, cur=cur, metadata=metadata)

    def error(self, message):
        raise SerializationError(self.obj, self.path, message)

    def assert_type(self, typ):
        if type(self.cur) is not typ:
            self.error("{!r} is not a {}".format(self.cur, typ))


class Deserializer:

    def __init__(self):
        self.typing_walkers = {
            list: self._walk_List,
            typing.List: self._walk_List,
            typing.Union: self._walk_Union,
            }
        self.type_deserializers = {}
        for typ in int, str, bool, list, dict, type(None):
            self.type_deserializers[typ] = self._scalar

    def _scalar(self, annotation, context):
        context.assert_type(annotation)
        return context.cur

    def _walk_List(self, meth, args, context):
        return [
            meth(args[0], context.child(f'[{i}]', v))
            for i, v in enumerate(context.cur)
            ]

    def _walk_Union(self, meth, args, context):
        if context.cur is None:
            return context.cur
        NoneType = type(None)
        if NoneType in args:
            args = [a for a in args if a is not NoneType]
            if len(args) == 1:
                # I.e. Optional[thing]
                return meth(args[0], context)
        if isinstance(context.cur, list):
            return meth(list, context)
        if isinstance(context.cur, str):
            return meth(str, context)
        context.error(f"cannot serialize Union[{args}]")

    def _deserialize_attr(self, annotation, context):
        context.assert_type(dict)
        args = {}
        fields = {
            field.name: field for field in attr.fields(annotation)
            }
        for key, value in context.cur.items():
            key = key.replace("-", "_")
            if key not in fields:
                continue
            field = fields[key]
            if field.converter:
                value = field.converter(value)
            args[field.name] = self._deserialize(
                field.type,
                context.child(f'[{key!r}]', value, field.metadata))
        return annotation(**args)

    def _deserialize(self, annotation, context):
        if annotation is None:
            context.assert_type(type(None))
            return None
        if annotation is typing.Any:
            return context.cur
        if attr.has(annotation):
            return self._deserialize_attr(annotation, context)
        origin = getattr(annotation, '__origin__', None)
        if origin is not None:
            return self.typing_walkers[origin](
                self._deserialize, annotation.__args__, context)
        return self.type_deserializers[annotation](annotation, context)

    def deserialize(self, annotation, value):
        context = SerializationContext.new(value)
        return self._deserialize(annotation, context)


T = typing.TypeVar("T")


def fromdict(cls: typing.Type[T], d) -> T:
    deserializer = Deserializer()
    return deserializer.deserialize(cls, d)


# vi: ts=4 expandtab syntax=python
