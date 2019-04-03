# This file is part of curtin. See LICENSE file for copyright and license info.
import copy
from collections import namedtuple, OrderedDict

from curtin.log import LOG
from curtin.block import schemas
from curtin import config as curtin_config


StorageConfig = namedtuple('StorageConfig', ('type', 'schema'))
STORAGE_CONFIG_TYPES = {
    'bcache': StorageConfig(type='bcache', schema=schemas.BCACHE),
    'disk': StorageConfig(type='disk', schema=schemas.DISK),
    'dm_crypt': StorageConfig(type='dm_crypt', schema=schemas.DM_CRYPT),
    'format': StorageConfig(type='format', schema=schemas.FORMAT),
    'lvm_partition': StorageConfig(type='lvm_partition',
                                   schema=schemas.LVM_PARTITION),
    'lvm_volgroup': StorageConfig(type='lvm_volgroup',
                                  schema=schemas.LVM_VOLGROUP),
    'mount': StorageConfig(type='mount', schema=schemas.MOUNT),
    'partition': StorageConfig(type='partition', schema=schemas.PARTITION),
    'raid': StorageConfig(type='raid', schema=schemas.RAID),
    'zfs': StorageConfig(type='zfs', schema=schemas.ZFS),
    'zpool': StorageConfig(type='zpool', schema=schemas.ZPOOL),
}


def get_storage_types():
    return copy.deepcopy(STORAGE_CONFIG_TYPES)


def get_storage_type_schemas():
    return [stype.schema for stype in sorted(get_storage_types().values())]


STORAGE_CONFIG_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'name': 'ASTORAGECONFIG',
    'title': 'curtin storage configuration for an installation.',
    'description': (
        'Declaritive syntax for specifying storage device configuration.'),
    'required': ['version', 'config'],
    'definitions': schemas.definitions,
    'properties': {
        'version': {'type': 'integer', 'enum': [1]},
        'config': {
            'type': 'array',
            'items': {
                'oneOf': get_storage_type_schemas(),
            },
            'additionalItems': False,
        },
    },
    'additionalProperties': False,
}


def load_and_validate(config_path):
    """Load and validate storage config file."""
    config = curtin_config.load_config(config_path)
    if 'storage' not in config:
        LOG.info('Skipping %s, missing "storage" key' % config_path)
        return

    return validate_config(config.get('storage'))


def validate_config(config):
    """Validate storage config object."""
    try:
        import jsonschema
        jsonschema.validate(config, STORAGE_CONFIG_SCHEMA)
    except jsonschema.exceptions.ValidationError as e:
        if isinstance(e.instance, int):
            msg = 'Unexpected value (%s) for property "%s"' % (e.path[0],
                                                               e.instance)
            raise ValueError(msg)
        if 'type' not in e.instance:
            msg = "%s in %s" % (e.message, e.instance)
            raise ValueError(msg)

        instance_type = e.instance['type']
        stype = get_storage_types().get(instance_type)
        if stype:
            try:
                jsonschema.validate(e.instance, stype.schema)
            except jsonschema.exceptions.ValidationError as f:
                msg = "%s in %s" % (f.message, e.instance)
                raise(ValueError(msg))
        else:
            msg = "Unknown storage type: %s in %s" % (instance_type,
                                                      e.instance)
            raise ValueError(msg)


# FIXME: move this map to each types schema and extract these
# values from each type's schema.
def _stype_to_deps(stype):
    """ Return a set of storage_config type keys for storage_config type.

        The strings returned in a dep set indicate which fields reference
        other storage_config elements that require a lookup.

        config:
         - type: disk
           id: sda
           path: /dev/sda
           ptable: gpt
         - type: partition
           id: sda1
           device: sda
    """

    depends_keys = {
        'bcache': set('backing_device', 'cache_device'),
        'disk': set(),
        'dm_crypt': set('volume'),
        'format': set('volume'),
        'lvm_partition': set('volgroup'),
        'lvm_volgroup': set('devices'),
        'mount': set('device'),
        'partition': set('device'),
        'raid': set('devices', 'spare_devices'),
        'zfs': set('pool'),
        'zpool': set('vdevs'),
    }
    return depends_keys[stype]


# Document what each storage type can be composed from.
def _validate_dep_type(source_id, dep_key, dep_id, sconfig):
    '''check if dependency type is in the list of allowed by source'''

    # FIXME: this should come from curtin.block.schemas.*
    depends = {
        'bcache': {'bcache', 'disk', 'dm_crypt', 'lvm_partition',
                   'partition', 'raid'},
        'disk': {},
        'dm_crypt': {'bcache', 'disk', 'dm_crypt', 'lvm_partition',
                     'partition', 'raid'},
        'format': {'bcache', 'disk', 'dm_crypt', 'lvm_partition',
                   'partition', 'raid'},
        'lvm_partition': {'lvm_volgroup'},
        'lvm_volgroup': {'bcache', 'disk', 'dm_crypt', 'partition', 'raid'},
        'mount': {'format'},
        'partition': {'bcache', 'disk', 'raid'},
        'raid': {'bcache', 'disk', 'dm_crypt', 'lvm_partition',
                 'partition'},
        'zfs': {'zpool'},
        'zpool': {'disk', 'partition'},
    }
    if source_id not in sconfig:
        raise ValueError(
                'Invalid source_id (%s) not in storage config' % source_id)
    if dep_id not in sconfig:
        raise ValueError(
                'Invalid dep_id (%s) not in storage config' % dep_id)

    source_type = sconfig[source_id]['type']
    dep_type = sconfig[dep_id]['type']

    if source_type not in depends:
        raise ValueError('Invalid source_type: %s' % source_type)
    if dep_type not in depends:
        raise ValueError('Invalid type in depedency: %s' % dep_type)

    source_deps = depends[source_type]
    result = dep_type in source_deps
    LOG.debug('Validate: SourceType:%s -> (DepId:%s DepType:%s) in '
              'SourceDeps:%s ? result=%s' % (source_type, dep_id, dep_type,
                                             source_deps, result))
    if not result:
        # Partition(sda1).device -> Partition(sda3)
        s_str = '%s(id=%s).%s' % (source_type.capitalize(),
                                  source_id, dep_key)
        d_str = '%s(id=%s)' % (dep_type.capitalize(), dep_id)
        dep_chain = "%s cannot depend upon on %s" % (s_str, d_str)
        raise ValueError(dep_chain)

    return result


def find_item_dependencies(item_id, config, validate=True):
    """ Walk a storage config collecting any dependent device ids."""

    if not config or not isinstance(config, OrderedDict):
        raise ValueError('Invalid config. Must be non-empty OrderedDict')

    item_cfg = config.get(item_id)
    if not item_cfg:
        return None

    deps = []
    item_type = item_cfg.get('type')
    for dep_key in _stype_to_deps(item_type):
        if dep_key in item_cfg:
            dep_value = item_cfg[dep_key]
            if not isinstance(dep_value, list):
                dep_value = [dep_value]
            deps.extend(dep_value)
            for dep in dep_value:
                if validate:
                    _validate_dep_type(item_id, dep_key, dep, config)

                d = find_item_dependencies(dep, config)
                if d:
                    deps.extend(d)

    return deps


def get_config_tree(item, storage_config):
    '''Construct an OrderedDict which inserts all of the
       storage config dependencies required to construct
       the device specifed by item_id.

    '''
    sconfig = extract_storage_ordered_dict(storage_config)
    # Create the OrderedDict by inserting the top-most item
    # and then inserting the next dependency.
    item_deps = OrderedDict({item: sconfig[item]})
    for dep in find_item_dependencies(item, sconfig):
        item_deps[dep] = sconfig[dep]
    return item_deps


def merge_config_trees_to_list(config_trees):
    ''' Create a registry to track each tree by
        device_id, and capture the dependency level
        and config of each tree.

        From this registry we can return a list that
        is sorted from the least to most dependent
        configuration item.  This calculation ensures
        that composed devices are listed last.
    '''

    reg = {}
    # reg[sda] = {level=0, config={}}
    # reg[sdd] = {level=0, config={}}
    # reg[sde] = {level=0, config={}}
    # reg[sdf] = {level=0, config={}}
    # reg[md0] = {level=3, config={'devices': [sdd, sde, sdf]}}
    # reg[sda5] = {level=1, config={'device': sda}}
    # reg[bcache1_raid] =
    #    {level=5, config={'backing': ['md0'], 'cache': ['sda5']}}
    max_level = 0
    for tree in config_trees:
        top_item_id = list(tree.keys())[0]  # first insertion has the most deps
        level = len(tree.keys())
        if level > max_level:
            max_level = level
        item_cfg = tree[top_item_id]
        if top_item_id in reg:
            raise ValueError('Duplicate id: %s' % top_item_id)
        reg[top_item_id] = {'level': level, 'config': item_cfg}

    # [entry for tag in tags]
    return [entry['config'] for lvl in range(0, max_level + 1)
            for _, entry in reg.items() if entry['level'] == lvl]


def config_tree_to_list(config_tree):
    """ ConfigTrees are OrderedDicts which insert dependent storage configs
        from leaf to root.  Reversing this insertion order creates a list
        of storage_configuration that is in the correct order for use by
        block_meta.
    """
    return [config_tree[item] for item in reversed(config_tree)]


def extract_storage_ordered_dict(config):
    storage_config = config.get('storage')
    if not storage_config:
        raise ValueError("no 'storage' entry in config")
    scfg = storage_config.get('config')
    if not scfg:
        raise ValueError("invalid storage config data")

    # Since storage config will often have to be searched for a value by its
    # id, and this can become very inefficient as storage_config grows, a dict
    # will be generated with the id of each component of the storage_config as
    # its index and the component of storage_config as its value
    return OrderedDict((d["id"], d) for d in scfg)

# vi: ts=4 expandtab syntax=python
