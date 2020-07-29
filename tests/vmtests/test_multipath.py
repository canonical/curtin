# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, load_config, sanitize_dname
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase
from curtin import util
from curtin.commands.block_meta import DNAME_BYID_KEYS

from unittest import SkipTest
import os
import textwrap


class TestMultipathBasicAbs(VMBaseClass):
    conf_file = "examples/tests/multipath.yaml"
    dirty_disks = True
    test_type = 'storage'
    multipath = True
    disk_driver = 'scsi-hd'
    extra_disks = []
    nvme_disks = []
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        multipath -ll > multipath_ll
        multipath -v3 -ll > multipath_v3_ll
        multipath -r > multipath_r
        cp -a /etc/multipath* .
        readlink -f /sys/class/block/sda/holders/dm-0 > holders_sda
        readlink -f /sys/class/block/sdb/holders/dm-0 > holders_sdb
        command -v systemctl && {
            systemctl show -- home.mount > systemctl_show_home.mount;
            systemctl status --full home.mount > systemctl_status_home.mount
        }
        for dev in $(ls /dev/dm-* /dev/sd?); do
            [ -b $dev ] && {
                udevadm info --query=property \
                    --export $dev > udevadm_info_$(basename $dev)
            }
        done
        cat /proc/cmdline > proc_cmdline
        exit 0
        """)]

    def test_dname_rules(self, disk_to_check=None):
        if self.target_distro != "ubuntu":
            raise SkipTest("dname not present in non-ubuntu releases")

        print('test_dname_rules: checking disks: %s', disk_to_check)
        self.output_files_exist(["udev_rules.d"])

        cfg = load_config(self.collect_path("root/curtin-install-cfg.yaml"))
        stgcfg = cfg.get("storage", {}).get("config", [])
        disks = [ent for ent in stgcfg if (ent.get('type') == 'disk' and
                                           'name' in ent)]
        for disk in disks:
            if not disk.get('name'):
                continue
            dname = sanitize_dname(disk.get('name'))
            dname_file = "%s.rules" % dname
            dm_dev = self._dname_to_kname(dname)
            info = util.load_shell_content(
                self.load_collect_file("udevadm_info_%s" % dm_dev))
            contents = self.load_collect_file("udev_rules.d/%s" % dname_file)

            present = [k for k in DNAME_BYID_KEYS if info.get(k)]
            # xenial and bionic do not have multipath in ephemeral environment
            # so dnames cannot use DM_UUID in rule files.
            if self.target_release in ['xenial', 'bionic', 'centos70']:
                present.remove('DM_UUID')
            if present:
                for id_key in present:
                    value = info[id_key]
                    if value:
                        self.assertIn(id_key, contents)
                        self.assertIn(value, contents)

    def test_multipath_disks_match(self):
        sda_data = self.load_collect_file("holders_sda")
        print('sda holders:\n%s' % sda_data)
        sdb_data = self.load_collect_file("holders_sdb")
        print('sdb holders:\n%s' % sdb_data)
        self.assertEqual(os.path.basename(sda_data),
                         os.path.basename(sdb_data))

    def test_home_mount_unit(self):
        unit_file = 'systemctl_show_home.mount'
        if not os.path.exists(self.collect_path(unit_file)):
            raise SkipTest(
                'target_release=%s does not use systemd' % self.target_release)

        # We can't use load_shell_content as systemctl show output
        # does not quote values even though it's in Key=Value format
        content = self.load_collect_file(unit_file)
        expected_results = {
            'ActiveState': 'active',
            'Result': 'success',
            'SubState': 'mounted',
        }
        show = {key: value for key, value in
                [line.split('=') for line in content.splitlines()
                 if line.split('=')[0] in expected_results.keys()]}

        self.assertEqual(expected_results, show)

    def get_fstab_expected(self):
        # xenial and bionic do not have multipath in ephemeral environment
        # so fstab entries are not DM_UUID based.
        if self.target_release in ['xenial', 'bionic', 'centos70']:
            return [
                (self._kname_to_byuuid('dm-1'), '/', 'defaults'),
                (self._kname_to_byuuid('dm-2'), '/home', 'defaults,nofail')]

        root = self._dname_to_kname('mpath_a-part1')
        home = self._dname_to_kname('mpath_a-part2')
        return [
            (self._kname_to_uuid_devpath('dm-uuid-part1-mpath', root),
             '/', 'defaults'),
            (self._kname_to_uuid_devpath('dm-uuid-part2-mpath', home),
             '/home', 'defaults,nofail')]

    def test_proc_command_line_has_mp_device(self):
        cmdline = self.load_collect_file('proc_cmdline')
        root = [tok for tok in cmdline.split() if tok.startswith('root=')]
        self.assertEqual(len(root), 1)

        root = root.pop()
        root = root.split('root=')[1]
        if self.target_release in ['xenial', 'bionic']:
            self.assertEqual('/dev/mapper/mpath0-part1', root)
        elif self.target_release in ['centos70']:
            self.assertEqual('/dev/mapper/mpath0p1', root)
        else:
            dm_dev = self._dname_to_kname('mpath_a-part1')
            info = util.load_shell_content(
                self.load_collect_file("udevadm_info_%s" % dm_dev))
            dev_mapper = '/dev/mapper/' + info['DM_NAME']
            self.assertEqual(dev_mapper, root)


class Centos70TestMultipathBasic(centos_relbase.centos70_xenial,
                                 TestMultipathBasicAbs):
    __test__ = True


class XenialGATestMultipathBasic(relbase.xenial_ga, TestMultipathBasicAbs):
    __test__ = True


class XenialHWETestMultipathBasic(relbase.xenial_hwe, TestMultipathBasicAbs):
    __test__ = True


class XenialEdgeTestMultipathBasic(relbase.xenial_edge, TestMultipathBasicAbs):
    __test__ = True


class BionicTestMultipathBasic(relbase.bionic, TestMultipathBasicAbs):
    __test__ = True


class FocalTestMultipathBasic(relbase.focal, TestMultipathBasicAbs):
    __test__ = True


class GroovyTestMultipathBasic(relbase.groovy, TestMultipathBasicAbs):
    __test__ = True


# vi: ts=4 expandtab syntax=python
