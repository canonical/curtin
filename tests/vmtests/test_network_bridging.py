from . import logger
from .releases import base_vm_classes as relbase
from .test_network import TestNetworkBaseTestsAbs
from curtin import util

import textwrap


bridge_param_to_sysfs = {
    'bridge_ageing': '/sys/class/net/{name}/bridge/ageing_time',
    'bridge_bridgeprio': '/sys/class/net/{name}/bridge/priority',
    'bridge_fd': '/sys/class/net/{name}/bridge/forward_delay',
    'bridge_hello': '/sys/class/net/{name}/bridge/hello_time',
    'bridge_hw': '/sys/class/net/{name}/address',
    'bridge_maxage': '/sys/class/net/{name}/bridge/max_age',
    'bridge_pathcost': '/sys/class/net/{name}/brif/{port}/path_cost',
    'bridge_portprio': '/sys/class/net/{name}/brif/{port}/priority',
    'bridge_stp': '/sys/class/net/{name}/bridge/stp_state',
}


# convert kernel sysfs values into human settings
bridge_param_divfactor = {
    'bridge_ageing': 100,
    'bridge_bridgeprio': 1,
    'bridge_fd': 100,
    'bridge_hello': 100,
    'bridge_maxage': 100,
    'bridge_pathcost': 1,
    'bridge_portprio': 1,
}

default_bridge_params_uncheckable = [
    'bridge_gcint',  # dead in kernel
    'bridge_maxwait',  # ifupdown variable
    'bridge_ports',  # not a sysfs value
    'bridge_waitport',  # ifupdown variable
]

# attrs we cannot validate
release_to_bridge_params_uncheckable = {
    'xenial': ['bridge_ageing'],
    'yakkety': ['bridge_ageing'],
}


def _get_sysfs_value(sysfs_data, name, param, port=None):
    """ Look up the correct sysfs file based on the network
        device `name`, the sysfs parameter, and in the case
        we're looking at a per-port setting, change how we
        index the the data.
    """
    print('_get_sys_val: name=%s param=%s port=%s' % (name, param, port))
    bcfg = {
        'name': name,
        'dataidx': name,
    }
    if port:
        bcfg.update({
            'port': port,
            'dataidx': port})
    print('_get_sys_val: bcfg: %s' % bcfg)

    # look up the param template and fill it out to find
    # which file holds the value
    sys_file = bridge_param_to_sysfs[param].format(**bcfg)
    print('_get_sys_val: sys_file=%s' % sys_file)

    # extract the value and convert to integer; this is an assumption
    # for bridge params.
    sys_file_val = int(sysfs_data[bcfg.get('dataidx')][sys_file])

    # Some of the kernel parameters are non-human values, in that
    # case convert them back to match values from the input YAML
    if param in bridge_param_divfactor:
        sys_file_val = (sys_file_val / bridge_param_divfactor[param])

    return sys_file_val


def sysfs_to_dict(input):
    """ Simple converter for loading key: value lines from a recursive
        grep -r . <sysfs path> > sysfs_data
    """
    data = util.load_file(input)

    return {y[0]: ":".join(y[1:]) for y in
            [x.split(":")for x in data.split("\n") if len(x) > 0]}


class TestBridgeNetworkAbs(TestNetworkBaseTestsAbs):
    conf_file = "examples/tests/bridging_network.yaml"
    collect_scripts = TestNetworkBaseTestsAbs.collect_scripts + [
        textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        grep -r . /sys/class/net/br0 > sysfs_br0
        grep -r . /sys/class/net/br0/brif/eth1 > sysfs_br0_eth1
        grep -r . /sys/class/net/br0/brif/eth2 > sysfs_br0_eth2
        dpkg-query -W -f '${Status}' bridge-utils 2>&1 > bridge-utils_installed
        """)]

    def test_output_files_exist_bridge(self):
        self.output_files_exist(["bridge-utils_installed",
                                 "sysfs_br0",
                                 "sysfs_br0_eth1",
                                 "sysfs_br0_eth2"])

    def test_bridge_utils_installed(self):
        status = self.load_collect_file("bridge-utils_installed").strip()
        logger.debug('bridge-utils installed: {}'.format(status))
        self.assertEqual('install ok installed', status)

    def test_bridge_params(self):
        """ Test if configure bridge params match values on the device """

        def _load_sysfs_bridge_data():
            sysfs_br0 = sysfs_to_dict(self.collect_path("sysfs_br0"))
            sysfs_br0_eth1 = sysfs_to_dict(self.collect_path("sysfs_br0_eth1"))
            sysfs_br0_eth2 = sysfs_to_dict(self.collect_path("sysfs_br0_eth2"))
            return {
                'br0': sysfs_br0,
                'eth1': sysfs_br0_eth1,
                'eth2': sysfs_br0_eth2,
            }

        def _get_bridge_config():
            network_state = self.get_network_state()
            interfaces = network_state.get('interfaces')
            br0 = interfaces.get('br0')
            return br0

        def _get_bridge_params(br):
            bridge_params_uncheckable = default_bridge_params_uncheckable
            bridge_params_uncheckable.extend(
                release_to_bridge_params_uncheckable.get(self.release, []))
            return [p for p in br.keys()
                    if (p.startswith('bridge_') and
                        p not in bridge_params_uncheckable)]

        def _check_bridge_param(sysfs_vals, p, br):
            value = br.get(param)
            if param in ['bridge_stp']:
                if value in ['off', '0']:
                    value = 0
                elif value in ['on', '1']:
                    value = 1
                else:
                    print('bridge_stp not in known val list')

            print('key=%s value=%s' % (param, value))
            if type(value) == list:
                for subval in value:
                    (port, pval) = subval.split(" ")
                    print('key=%s port=%s pval=%s' % (param, port, pval))
                    sys_file_val = _get_sysfs_value(sysfs_vals, br0['name'],
                                                    param, port)

                    self.assertEqual(int(pval), int(sys_file_val))
            else:
                sys_file_val = _get_sysfs_value(sysfs_vals, br0['name'],
                                                param, port=None)
                self.assertEqual(int(value), int(sys_file_val))

        sysfs_vals = _load_sysfs_bridge_data()
        print(sysfs_vals)
        br0 = _get_bridge_config()
        for param in _get_bridge_params(br0):
            _check_bridge_param(sysfs_vals, param, br0)


# only testing Yakkety or newer as older releases do not yet
# have updated ifupdown/bridge-utils packages;
class YakketyTestBridging(relbase.yakkety, TestBridgeNetworkAbs):
    __test__ = True


class ZestyTestBridging(relbase.zesty, TestBridgeNetworkAbs):
    __test__ = True


class ArtfulTestBridging(relbase.artful, TestBridgeNetworkAbs):
    __test__ = True
