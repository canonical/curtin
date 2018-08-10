from . import VMBaseClass, check_install_log, skip_if_flag
from .releases import base_vm_classes as relbase

import textwrap


class TestZfsRootAbs(VMBaseClass):
    interactive = False
    nr_cpus = 2
    dirty_disks = True
    conf_file = "examples/tests/zfsroot.yaml"
    extra_disks = []
    collect_scripts = VMBaseClass.collect_scripts + [
        textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            blkid -o export /dev/vda > blkid_output_vda
            blkid -o export /dev/vda1 > blkid_output_vda1
            blkid -o export /dev/vda2 > blkid_output_vda2
            zfs list > zfs_list
            zpool list > zpool_list
            zpool status > zpool_status
            cat /proc/partitions > proc_partitions
            cat /proc/mounts > proc_mounts
            cat /proc/cmdline > proc_cmdline
            ls -al /dev/disk/by-uuid/ > ls_uuid
            cat /etc/fstab > fstab
            mkdir -p /dev/disk/by-dname
            ls /dev/disk/by-dname/ > ls_dname
            find /etc/network/interfaces.d > find_interfacesd
            v=""
            out=$(apt-config shell v Acquire::HTTP::Proxy)
            eval "$out"
            echo "$v" > apt-proxy
        """)]

    @skip_if_flag('expected_failure')
    def test_output_files_exist(self):
        self.output_files_exist(
            ["blkid_output_vda", "blkid_output_vda1", "blkid_output_vda2",
             "fstab", "ls_dname", "ls_uuid",
             "proc_partitions",
             "root/curtin-install.log", "root/curtin-install-cfg.yaml"])

    @skip_if_flag('expected_failure')
    def test_ptable(self):
        blkid_info = self.get_blkid_data("blkid_output_vda")
        self.assertEquals(blkid_info["PTTYPE"], "gpt")

    @skip_if_flag('expected_failure')
    def test_zfs_list(self):
        """Check rpoot/ROOT/zfsroot is mounted at slash"""
        self.output_files_exist(['zfs_list'])
        self.check_file_regex('zfs_list', r"rpool/ROOT/zfsroot.*/\n")

    @skip_if_flag('expected_failure')
    def test_proc_cmdline_has_root_zfs(self):
        """Check /proc/cmdline has root=ZFS=<pool>"""
        self.output_files_exist(['proc_cmdline'])
        self.check_file_regex('proc_cmdline', r"root=ZFS=rpool/ROOT/zfsroot")


class UnsupportedZfs(VMBaseClass):
    expected_failure = True
    collect_scripts = []
    interactive = False

    def test_install_log_finds_zfs_runtime_error(self):
        with open(self.install_log, 'rb') as lfh:
            install_log = lfh.read().decode('utf-8', errors='replace')
        errmsg, errors = check_install_log(install_log)
        found_zfs = False
        print("errors: %s" % (len(errors)))
        for idx, err in enumerate(errors):
            print("%s:\n%s" % (idx, err))
            if 'RuntimeError' in err:
                found_zfs = True
                break
        self.assertTrue(found_zfs)


class XenialGAi386TestZfsRoot(relbase.xenial_ga, TestZfsRootAbs,
                              UnsupportedZfs):
    __test__ = True
    arch = 'i386'


class XenialGATestZfsRoot(relbase.xenial_ga, TestZfsRootAbs):
    __test__ = True


class XenialHWETestZfsRoot(relbase.xenial_hwe, TestZfsRootAbs):
    __test__ = True


class XenialEdgeTestZfsRoot(relbase.xenial_edge, TestZfsRootAbs):
    __test__ = True


class BionicTestZfsRoot(relbase.bionic, TestZfsRootAbs):
    __test__ = True


class CosmicTestZfsRoot(relbase.cosmic, TestZfsRootAbs):
    __test__ = True


class TestZfsRootFsTypeAbs(TestZfsRootAbs):
    conf_file = "examples/tests/basic-zfsroot.yaml"


class XenialGATestZfsRootFsType(relbase.xenial_ga, TestZfsRootFsTypeAbs):
    __test__ = True


class XenialGAi386TestZfsRootFsType(relbase.xenial_ga, TestZfsRootFsTypeAbs,
                                    UnsupportedZfs):
    __test__ = True
    arch = 'i386'


class BionicTestZfsRootFsType(relbase.bionic, TestZfsRootFsTypeAbs):
    __test__ = True


class CosmicTestZfsRootFsType(relbase.cosmic, TestZfsRootFsTypeAbs):
    __test__ = True
