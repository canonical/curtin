from . import VMBaseClass, check_install_log, skip_if_flag
from .releases import base_vm_classes as relbase

import textwrap


class TestZfsRootAbs(VMBaseClass):
    interactive = False
    test_type = 'storage'
    nr_cpus = 2
    dirty_disks = True
    conf_file = "examples/tests/zfsroot.yaml"
    extra_disks = []
    extra_collect_scripts = [textwrap.dedent("""
            cd OUTPUT_COLLECT_D
            blkid -o export /dev/vda > blkid_output_vda
            zfs list > zfs_list
            zpool list > zpool_list
            zpool status > zpool_status
            zdb > zdb.output
            cp -a /etc/zfs ./etc_zfs

            exit 0
        """)]

    @skip_if_flag('expected_failure')
    def test_output_files_exist(self):
        self.output_files_exist(["root/curtin-install.log",
                                 "root/curtin-install-cfg.yaml"])

    @skip_if_flag('expected_failure')
    def test_ptable(self):
        self.output_files_exist(["blkid_output_vda"])
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

    @skip_if_flag('expected_failure')
    def test_etc_zfs_has_zpool_cache(self):
        """Check /etc/zfs/zpoolcache exists"""
        self.output_files_exist(['etc_zfs/zpool.cache'])


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


class DiscoTestZfsRoot(relbase.disco, TestZfsRootAbs):
    __test__ = True
    mem = 4096


class EoanTestZfsRoot(relbase.eoan, TestZfsRootAbs):
    __test__ = True
    mem = 4096


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


class DiscoTestZfsRootFsType(relbase.disco, TestZfsRootFsTypeAbs):
    __test__ = True
    mem = 4096


class EoanTestZfsRootFsType(relbase.eoan, TestZfsRootFsTypeAbs):
    __test__ = True
    mem = 4096
