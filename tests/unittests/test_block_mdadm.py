from unittest import TestCase
from mock import call, patch
from curtin.block import dev_short
from curtin.block import mdadm
from curtin import util
import os
import subprocess
import textwrap


class MdadmTestBase(TestCase):
    def setUp(self):
        super(MdadmTestBase, self).setUp()

    def add_patch(self, target, attr):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        m = patch(target, autospec=True)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)


class TestBlockMdadmAssemble(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmAssemble, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')
        self.add_patch('curtin.block.mdadm.udev', 'mock_udev')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'precise'}
        self.mock_util.subp.return_value = ('', '')

    def test_mdadm_assemble_scan(self):
        mdadm.mdadm_assemble(scan=True)
        assemble_calls = [
            call(["mdadm", "--assemble", "--scan", "-v"], capture=True,
                 rcs=[0, 1, 2]),
            call(["mdadm", "--detail", "--scan", "-v"], capture=True,
                 rcs=[0, 1]),
        ]
        self.mock_util.subp.assert_has_calls(assemble_calls)
        self.assertTrue(self.mock_udev.udevadm_settle.called)

    def test_mdadm_assemble_md_devname(self):
        md_devname = "/dev/md0"
        mdadm.mdadm_assemble(md_devname=md_devname)

        assemble_calls = [
            call(["mdadm", "--assemble", md_devname, "--run"],
                 capture=True, rcs=[0, 1, 2]),
            call(["mdadm", "--detail", "--scan", "-v"], capture=True,
                 rcs=[0, 1]),
        ]
        self.mock_util.subp.assert_has_calls(assemble_calls)
        self.assertTrue(self.mock_udev.udevadm_settle.called)

    def test_mdadm_assemble_md_devname_short(self):
        with self.assertRaises(ValueError):
            md_devname = "md0"
            mdadm.mdadm_assemble(md_devname=md_devname)

    def test_mdadm_assemble_md_devname_none(self):
        with self.assertRaises(ValueError):
            md_devname = None
            mdadm.mdadm_assemble(md_devname=md_devname)

    def test_mdadm_assemble_md_devname_devices(self):
        md_devname = "/dev/md0"
        devices = ["/dev/vdc1", "/dev/vdd1"]
        mdadm.mdadm_assemble(md_devname=md_devname, devices=devices)
        assemble_calls = [
            call(["mdadm", "--assemble", md_devname, "--run"] + devices,
                 capture=True, rcs=[0, 1, 2]),
            call(["mdadm", "--detail", "--scan", "-v"], capture=True,
                 rcs=[0, 1]),
        ]
        self.mock_util.subp.assert_has_calls(assemble_calls)
        self.assertTrue(self.mock_udev.udevadm_settle.called)

    def test_mdadm_assemble_exec_error(self):

        def _raise_pexec_error(*args, **kwargs):
            raise util.ProcessExecutionError()

        self.mock_util.ProcessExecutionError = util.ProcessExecutionError
        self.mock_util.subp.side_effect = _raise_pexec_error
        with self.assertRaises(util.ProcessExecutionError):
            mdadm.mdadm_assemble(scan=True, ignore_errors=False)
        self.mock_util.subp.assert_called_with(
            ['mdadm', '--assemble', '--scan', '-v'], capture=True,
            rcs=[0, 1, 2])


class TestBlockMdadmCreate(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmCreate, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')
        self.add_patch('curtin.block.mdadm.get_holders', 'mock_holders')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'precise'}
        self.mock_holders.return_value = []

    def prepare_mock(self, md_devname, raidlevel, devices, spares):
        side_effects = []
        expected_calls = []
        hostname = 'ubuntu'

        # don't mock anything if raidlevel and spares mismatch
        if spares and raidlevel not in mdadm.SPARE_RAID_LEVELS:
            return (side_effects, expected_calls)

        side_effects.append((hostname, ""))  # hostname -s
        expected_calls.append(call(["hostname", "-s"],
                                   capture=True, rcs=[0]))

        # prepare side-effects
        for d in devices + spares:
            side_effects.append(("", ""))  # mdadm --zero-superblock
            expected_calls.append(
                call(["mdadm", "--zero-superblock", d], capture=True))

        side_effects.append(("", ""))  # udevadm settle
        expected_calls.append(call(["udevadm", "settle"]))
        side_effects.append(("", ""))  # udevadm control --stop-exec-queue
        expected_calls.append(call(["udevadm", "control",
                                    "--stop-exec-queue"]))

        side_effects.append(("", ""))  # mdadm create
        # build command how mdadm_create does
        cmd = (["mdadm", "--create", md_devname, "--run",
                "--homehost=%s" % hostname, "--level=%s" % raidlevel,
                "--raid-devices=%s" % len(devices)] +
               devices)
        if spares:
            cmd += ["--spare-devices=%s" % len(spares)] + spares

        expected_calls.append(call(cmd, capture=True))
        side_effects.append(("", ""))  # udevadm control --start-exec-queue
        expected_calls.append(call(["udevadm", "control",
                                    "--start-exec-queue"]))
        side_effects.append(("", ""))  # udevadm settle
        expected_calls.append(call(["udevadm", "settle",
                                    "--exit-if-exists=%s" % md_devname]))

        return (side_effects, expected_calls)

    def test_mdadm_create_raid0(self):
        md_devname = "/dev/md0"
        raidlevel = 0
        devices = ["/dev/vdc1", "/dev/vdd1"]
        spares = []
        (side_effects, expected_calls) = self.prepare_mock(md_devname,
                                                           raidlevel,
                                                           devices,
                                                           spares)

        self.mock_util.subp.side_effect = side_effects
        mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                           devices=devices, spares=spares)
        self.mock_util.subp.assert_has_calls(expected_calls)

    def test_mdadm_create_raid0_devshort(self):
        md_devname = "md0"
        raidlevel = 0
        devices = ["/dev/vdc1", "/dev/vdd1"]
        spares = []
        with self.assertRaises(ValueError):
            mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                               devices=devices, spares=spares)

    def test_mdadm_create_raid0_with_spares(self):
        md_devname = "/dev/md0"
        raidlevel = 0
        devices = ["/dev/vdc1", "/dev/vdd1"]
        spares = ["/dev/vde1"]
        (side_effects, expected_calls) = self.prepare_mock(md_devname,
                                                           raidlevel,
                                                           devices,
                                                           spares)

        self.mock_util.subp.side_effect = side_effects
        with self.assertRaises(ValueError):
            mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                               devices=devices, spares=spares)
        self.mock_util.subp.assert_has_calls(expected_calls)

    def test_mdadm_create_md_devname_none(self):
        md_devname = None
        raidlevel = 0
        devices = ["/dev/vdc1", "/dev/vdd1"]
        spares = ["/dev/vde1"]
        with self.assertRaises(ValueError):
            mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                               devices=devices, spares=spares)

    def test_mdadm_create_md_devname_missing(self):
        self.mock_valid.return_value = False
        md_devname = "/dev/wark"
        raidlevel = 0
        devices = ["/dev/vdc1", "/dev/vdd1"]
        spares = ["/dev/vde1"]
        with self.assertRaises(ValueError):
            mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                               devices=devices, spares=spares)

    def test_mdadm_create_invalid_raidlevel(self):
        md_devname = "/dev/md0"
        raidlevel = 27
        devices = ["/dev/vdc1", "/dev/vdd1"]
        spares = ["/dev/vde1"]
        with self.assertRaises(ValueError):
            mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                               devices=devices, spares=spares)

    def test_mdadm_create_check_min_devices(self):
        md_devname = "/dev/md0"
        raidlevel = 5
        devices = ["/dev/vdc1", "/dev/vdd1"]
        spares = ["/dev/vde1"]
        with self.assertRaises(ValueError):
            mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                               devices=devices, spares=spares)

    def test_mdadm_create_raid5(self):
        md_devname = "/dev/md0"
        raidlevel = 5
        devices = ['/dev/vdc1', '/dev/vdd1', '/dev/vde1']
        spares = ['/dev/vdg1']
        (side_effects, expected_calls) = self.prepare_mock(md_devname,
                                                           raidlevel,
                                                           devices,
                                                           spares)

        self.mock_util.subp.side_effect = side_effects
        mdadm.mdadm_create(md_devname=md_devname, raidlevel=raidlevel,
                           devices=devices, spares=spares)
        self.mock_util.subp.assert_has_calls(expected_calls)


class TestBlockMdadmExamine(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmExamine, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'precise'}

    def test_mdadm_examine_export(self):
        self.mock_util.lsb_release.return_value = {'codename': 'xenial'}
        self.mock_util.subp.return_value = (
            """
            MD_LEVEL=raid0
            MD_DEVICES=2
            MD_METADATA=0.90
            MD_UUID=93a73e10:427f280b:b7076c02:204b8f7a
            """, "")

        device = "/dev/vde"
        data = mdadm.mdadm_examine(device, export=True)

        expected_calls = [
            call(["mdadm", "--examine", "--export", device], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)
        self.assertEqual(data['MD_UUID'],
                         '93a73e10:427f280b:b7076c02:204b8f7a')

    def test_mdadm_examine_no_export(self):
        self.mock_util.subp.return_value = ("""/dev/vde:
              Magic : a92b4efc
            Version : 1.2
        Feature Map : 0x0
         Array UUID : 93a73e10:427f280b:b7076c02:204b8f7a
               Name : wily-foobar:0  (local to host wily-foobar)
      Creation Time : Sat Dec 12 16:06:05 2015
         Raid Level : raid1
       Raid Devices : 2

     Avail Dev Size : 20955136 (9.99 GiB 10.73 GB)
      Used Dev Size : 20955136 (9.99 GiB 10.73 GB)
         Array Size : 10477568 (9.99 GiB 10.73 GB)
        Data Offset : 16384 sectors
       Super Offset : 8 sectors
       Unused Space : before=16296 sectors, after=0 sectors
              State : clean
        Device UUID : 8fcd62e6:991acc6e:6cb71ee3:7c956919

        Update Time : Sat Dec 12 16:09:09 2015
      Bad Block Log : 512 entries available at offset 72 sectors
           Checksum : 65b57c2e - correct
             Events : 17


       Device Role : spare
       Array State : AA ('A' == active, '.' == missing, 'R' == replacing)
        """, "")   # mdadm --examine /dev/vde

        device = "/dev/vde"
        data = mdadm.mdadm_examine(device, export=False)

        expected_calls = [
            call(["mdadm", "--examine", device], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)
        self.assertEqual(data['MD_UUID'],
                         '93a73e10:427f280b:b7076c02:204b8f7a')

    def test_mdadm_examine_no_raid(self):
        self.mock_util.subp.side_effect = subprocess.CalledProcessError("", "")

        device = "/dev/sda"
        data = mdadm.mdadm_examine(device, export=False)

        expected_calls = [
            call(["mdadm", "--examine", device], capture=True),
        ]

        # don't mock anything if raidlevel and spares mismatch
        self.mock_util.subp.assert_has_calls(expected_calls)
        self.assertEqual(data, {})


class TestBlockMdadmStop(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmStop, self).setUp()
        self.add_patch('curtin.block.mdadm.util.lsb_release', 'mock_util_lsb')
        self.add_patch('curtin.block.mdadm.util.subp', 'mock_util_subp')
        self.add_patch('curtin.block.mdadm.util.write_file',
                       'mock_util_write_file')
        self.add_patch('curtin.block.mdadm.util.load_file',
                       'mock_util_load_file')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')
        self.add_patch('curtin.block.mdadm.sys_block_path',
                       'mock_sys_block_path')
        self.add_patch('curtin.block.mdadm.os.path.isfile', 'mock_path_isfile')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util_lsb.return_value = {'codename': 'xenial'}
        self.mock_util_subp.side_effect = iter([
            ("", ""),  # mdadm stop device
        ])
        self.mock_path_isfile.return_value = True
        self.mock_util_load_file.side_effect = iter([
            "idle", "max",
        ])

    def _set_sys_path(self, md_device):
        self.sys_path = '/sys/class/block/%s/md' % md_device.split("/")[-1]
        self.mock_sys_block_path.return_value = self.sys_path

    def test_mdadm_stop_no_devpath(self):
        with self.assertRaises(ValueError):
            mdadm.mdadm_stop(None)

    def test_mdadm_stop(self):
        device = "/dev/md0"
        self._set_sys_path(device)

        mdadm.mdadm_stop(device)

        expected_calls = [
            call(["mdadm", "--manage", "--stop", device], capture=True)
        ]
        self.mock_util_subp.assert_has_calls(expected_calls)

        expected_reads = [
            call(self.sys_path + '/sync_action'),
            call(self.sys_path + '/sync_max'),
        ]
        self.mock_util_load_file.assert_has_calls(expected_reads)

    @patch('curtin.block.mdadm.time.sleep')
    def test_mdadm_stop_retry(self, mock_sleep):
        device = "/dev/md10"
        self._set_sys_path(device)
        self.mock_util_load_file.side_effect = iter([
            "resync", "max",
            "proc/mdstat output",
            "idle", "0",
        ])
        self.mock_util_subp.side_effect = iter([
            util.ProcessExecutionError(),
            ("mdadm stopped %s" % device, ''),
        ])

        mdadm.mdadm_stop(device)

        expected_calls = [
            call(["mdadm", "--manage", "--stop", device], capture=True),
            call(["mdadm", "--manage", "--stop", device], capture=True)
        ]
        self.mock_util_subp.assert_has_calls(expected_calls)

        expected_reads = [
            call(self.sys_path + '/sync_action'),
            call(self.sys_path + '/sync_max'),
            call('/proc/mdstat'),
            call(self.sys_path + '/sync_action'),
            call(self.sys_path + '/sync_max'),
        ]
        self.mock_util_load_file.assert_has_calls(expected_reads)

        expected_writes = [
            call(self.sys_path + '/sync_action', content='idle'),
            call(self.sys_path + '/sync_max', content='0'),
            call(self.sys_path + '/sync_min', content='0'),
        ]
        self.mock_util_write_file.assert_has_calls(expected_writes)

    @patch('curtin.block.mdadm.time.sleep')
    def test_mdadm_stop_retry_sysfs_write_fail(self, mock_sleep):
        device = "/dev/md126"
        self._set_sys_path(device)
        self.mock_util_load_file.side_effect = iter([
            "resync", "max",
            "proc/mdstat output",
            "idle", "0",
        ])
        self.mock_util_subp.side_effect = iter([
            util.ProcessExecutionError(),
            ("mdadm stopped %s" % device, ''),
        ])
        # sometimes we fail to modify sysfs attrs
        self.mock_util_write_file.side_effect = iter([
            "",         # write to sync_action OK
            IOError(),  # write to sync_max FAIL
        ])

        mdadm.mdadm_stop(device)

        expected_calls = [
            call(["mdadm", "--manage", "--stop", device], capture=True),
            call(["mdadm", "--manage", "--stop", device], capture=True)
        ]
        self.mock_util_subp.assert_has_calls(expected_calls)

        expected_reads = [
            call(self.sys_path + '/sync_action'),
            call(self.sys_path + '/sync_max'),
            call('/proc/mdstat'),
            call(self.sys_path + '/sync_action'),
            call(self.sys_path + '/sync_max'),
        ]
        self.mock_util_load_file.assert_has_calls(expected_reads)

        expected_writes = [
            call(self.sys_path + '/sync_action', content='idle'),
        ]
        self.mock_util_write_file.assert_has_calls(expected_writes)

    @patch('curtin.block.mdadm.time.sleep')
    def test_mdadm_stop_retry_exhausted(self, mock_sleep):
        device = "/dev/md/37"
        retries = 60
        self._set_sys_path(device)
        self.mock_util_load_file.side_effect = iter([
            "resync", "max",
            "proc/mdstat output",
        ] * retries)
        self.mock_util_subp.side_effect = iter([
            util.ProcessExecutionError(),
        ] * retries)
        # sometimes we fail to modify sysfs attrs
        self.mock_util_write_file.side_effect = iter([
            "", IOError()] * retries)

        with self.assertRaises(OSError):
            mdadm.mdadm_stop(device)

        expected_calls = [
            call(["mdadm", "--manage", "--stop", device], capture=True),
        ] * retries
        self.mock_util_subp.assert_has_calls(expected_calls)

        expected_reads = [
            call(self.sys_path + '/sync_action'),
            call(self.sys_path + '/sync_max'),
            call('/proc/mdstat'),
        ] * retries
        self.mock_util_load_file.assert_has_calls(expected_reads)

        expected_writes = [
            call(self.sys_path + '/sync_action', content='idle'),
            call(self.sys_path + '/sync_max', content='0'),
        ] * retries
        self.mock_util_write_file.assert_has_calls(expected_writes)


class TestBlockMdadmRemove(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmRemove, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'xenial'}
        self.mock_util.subp.side_effect = [
            ("", ""),  # mdadm remove device
        ]

    def test_mdadm_remove_no_devpath(self):
        with self.assertRaises(ValueError):
            mdadm.mdadm_remove(None)

    def test_mdadm_remove(self):
        device = "/dev/vdc"
        mdadm.mdadm_remove(device)
        expected_calls = [
            call(["mdadm", "--remove", device], rcs=[0], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)


class TestBlockMdadmQueryDetail(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmQueryDetail, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'precise'}

    def test_mdadm_query_detail_export(self):
        self.mock_util.lsb_release.return_value = {'codename': 'xenial'}
        self.mock_util.subp.return_value = (
            """
            MD_LEVEL=raid1
            MD_DEVICES=2
            MD_METADATA=1.2
            MD_UUID=93a73e10:427f280b:b7076c02:204b8f7a
            MD_NAME=wily-foobar:0
            MD_DEVICE_vdc_ROLE=0
            MD_DEVICE_vdc_DEV=/dev/vdc
            MD_DEVICE_vdd_ROLE=1
            MD_DEVICE_vdd_DEV=/dev/vdd
            MD_DEVICE_vde_ROLE=spare
            MD_DEVICE_vde_DEV=/dev/vde
            """, "")

        device = "/dev/md0"
        self.mock_valid.return_value = True
        data = mdadm.mdadm_query_detail(device, export=True)

        expected_calls = [
            call(["mdadm", "--query", "--detail", "--export", device],
                 capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)
        self.assertEqual(data['MD_UUID'],
                         '93a73e10:427f280b:b7076c02:204b8f7a')

    def test_mdadm_query_detail_no_export(self):
        self.mock_util.subp.return_value = ("""/dev/md0:
        Version : 1.2
  Creation Time : Sat Dec 12 16:06:05 2015
     Raid Level : raid1
     Array Size : 10477568 (9.99 GiB 10.73 GB)
  Used Dev Size : 10477568 (9.99 GiB 10.73 GB)
   Raid Devices : 2
  Total Devices : 3
    Persistence : Superblock is persistent

    Update Time : Sat Dec 12 16:09:09 2015
          State : clean
 Active Devices : 2
Working Devices : 3
 Failed Devices : 0
  Spare Devices : 1

           Name : wily-foobar:0  (local to host wily-foobar)
           UUID : 93a73e10:427f280b:b7076c02:204b8f7a
         Events : 17

    Number   Major   Minor   RaidDevice State
       0     253       32        0      active sync   /dev/vdc
       1     253       48        1      active sync   /dev/vdd

       2     253       64        -      spare   /dev/vde
        """, "")   # mdadm --query --detail /dev/md0

        device = "/dev/md0"
        data = mdadm.mdadm_query_detail(device, export=False)
        expected_calls = [
            call(["mdadm", "--query", "--detail", device], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)
        self.assertEqual(data['MD_UUID'],
                         '93a73e10:427f280b:b7076c02:204b8f7a')


class TestBlockMdadmDetailScan(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmDetailScan, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        # Common mock settings
        self.scan_output = ("ARRAY /dev/md0 metadata=1.2 spares=2 name=0 " +
                            "UUID=b1eae2ff:69b6b02e:1d63bb53:ddfa6e4a")
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'xenial'}
        self.mock_util.subp.side_effect = [
            (self.scan_output, ""),  # mdadm --detail --scan
        ]

    def test_mdadm_remove(self):
        data = mdadm.mdadm_detail_scan()
        expected_calls = [
            call(["mdadm", "--detail", "--scan"], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)
        self.assertEqual(self.scan_output, data)

    def test_mdadm_remove_error(self):
        self.mock_util.subp.side_effect = [
            ("wark", "error"),  # mdadm --detail --scan
        ]
        data = mdadm.mdadm_detail_scan()
        expected_calls = [
            call(["mdadm", "--detail", "--scan"], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)
        self.assertEqual(None, data)


class TestBlockMdadmMdHelpers(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmMdHelpers, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'xenial'}

    def test_valid_mdname(self):
        mdname = "/dev/md0"
        result = mdadm.valid_mdname(mdname)
        expected_calls = [
            call(mdname)
        ]
        self.mock_valid.assert_has_calls(expected_calls)
        self.assertTrue(result)

    def test_valid_mdname_short(self):
        mdname = "md0"
        with self.assertRaises(ValueError):
            mdadm.valid_mdname(mdname)

    def test_valid_mdname_none(self):
        mdname = None
        with self.assertRaises(ValueError):
            mdadm.valid_mdname(mdname)

    def test_valid_mdname_not_valid_device(self):
        self.mock_valid.return_value = False
        mdname = "/dev/md0"
        with self.assertRaises(ValueError):
            mdadm.valid_mdname(mdname)

    @patch('curtin.block.mdadm.sys_block_path')
    @patch('curtin.block.mdadm.os.path.isfile')
    def test_md_sysfs_attr(self, mock_isfile, mock_sysblock):
        mdname = "/dev/md0"
        attr_name = 'array_state'
        sysfs_path = '/sys/class/block/{}/md/{}'.format(dev_short(mdname),
                                                        attr_name)
        mock_sysblock.side_effect = ['/sys/class/block/md0/md']
        mock_isfile.side_effect = [True]
        mdadm.md_sysfs_attr(mdname, attr_name)
        self.mock_util.load_file.assert_called_with(sysfs_path)
        mock_sysblock.assert_called_with(mdname, 'md')
        mock_isfile.assert_called_with(sysfs_path)

    def test_md_sysfs_attr_devname_none(self):
        mdname = None
        attr_name = 'array_state'
        with self.assertRaises(ValueError):
            mdadm.md_sysfs_attr(mdname, attr_name)

    def test_md_raidlevel_short(self):
        for rl in [0, 1, 5, 6, 10, 'linear', 'stripe']:
            self.assertEqual(rl, mdadm.md_raidlevel_short(rl))
            if isinstance(rl, int):
                long_rl = 'raid%d' % rl
                self.assertEqual(rl, mdadm.md_raidlevel_short(long_rl))

    def test_md_minimum_devices(self):
        min_to_rl = {
            2: [0, 1, 'linear', 'stripe'],
            3: [5],
            4: [6, 10],
        }

        for rl in [0, 1, 5, 6, 10, 'linear', 'stripe']:
            min_devs = mdadm.md_minimum_devices(rl)
            self.assertTrue(rl in min_to_rl[min_devs])

    def test_md_minimum_devices_invalid_rl(self):
        min_devs = mdadm.md_minimum_devices(27)
        self.assertEqual(min_devs, -1)

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_rw(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.return_value = 'clean'
        self.assertTrue(mdadm.md_check_array_state_rw(mdname))

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_rw_false(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.return_value = 'inactive'
        self.assertFalse(mdadm.md_check_array_state_rw(mdname))

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_ro(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.return_value = 'readonly'
        self.assertTrue(mdadm.md_check_array_state_ro(mdname))

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_ro_false(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.return_value = 'inactive'
        self.assertFalse(mdadm.md_check_array_state_ro(mdname))

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_error(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.return_value = 'inactive'
        self.assertTrue(mdadm.md_check_array_state_error(mdname))

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_error_false(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.return_value = 'active'
        self.assertFalse(mdadm.md_check_array_state_error(mdname))

    def test_md_device_key_role(self):
        devname = '/dev/vda'
        rolekey = mdadm.md_device_key_role(devname)
        self.assertEqual('MD_DEVICE_vda_ROLE', rolekey)

    def test_md_device_key_role_no_dev(self):
        devname = None
        with self.assertRaises(ValueError):
            mdadm.md_device_key_role(devname)

    def test_md_device_key_dev(self):
        devname = '/dev/vda'
        devkey = mdadm.md_device_key_dev(devname)
        self.assertEqual('MD_DEVICE_vda_DEV', devkey)

    def test_md_device_key_dev_no_dev(self):
        devname = None
        with self.assertRaises(ValueError):
            mdadm.md_device_key_dev(devname)

    @patch('curtin.block.get_blockdev_for_partition')
    @patch('curtin.block.mdadm.os.path.exists')
    @patch('curtin.block.mdadm.os.listdir')
    def tests_md_get_spares_list(self, mock_listdir, mock_exists,
                                 mock_getbdev):
        mdname = '/dev/md0'
        devices = ['dev-vda', 'dev-vdb', 'dev-vdc']
        states = ['in-sync', 'in-sync', 'spare']

        mock_exists.return_value = True
        mock_listdir.return_value = devices
        self.mock_util.load_file.side_effect = states
        mock_getbdev.return_value = ('md0', None)

        sysfs_path = '/sys/class/block/md0/md/'

        expected_calls = []
        for d in devices:
            expected_calls.append(call(os.path.join(sysfs_path, d, 'state')))

        spares = mdadm.md_get_spares_list(mdname)
        self.mock_util.load_file.assert_has_calls(expected_calls)
        self.assertEqual(['/dev/vdc'], spares)

    @patch('curtin.block.get_blockdev_for_partition')
    @patch('curtin.block.mdadm.os.path.exists')
    def tests_md_get_spares_list_nomd(self, mock_exists, mock_getbdev):
        mdname = '/dev/md0'
        mock_exists.return_value = False
        mock_getbdev.return_value = ('md0', None)
        with self.assertRaises(OSError):
            mdadm.md_get_spares_list(mdname)

    @patch('curtin.block.get_blockdev_for_partition')
    @patch('curtin.block.mdadm.os.path.exists')
    @patch('curtin.block.mdadm.os.listdir')
    def tests_md_get_devices_list(self, mock_listdir, mock_exists,
                                  mock_getbdev):
        mdname = '/dev/md0'
        devices = ['dev-vda', 'dev-vdb', 'dev-vdc']
        states = ['in-sync', 'in-sync', 'spare']

        mock_exists.return_value = True
        mock_listdir.return_value = devices
        self.mock_util.load_file.side_effect = states
        mock_getbdev.return_value = ('md0', None)

        sysfs_path = '/sys/class/block/md0/md/'

        expected_calls = []
        for d in devices:
            expected_calls.append(call(os.path.join(sysfs_path, d, 'state')))

        devs = mdadm.md_get_devices_list(mdname)
        self.mock_util.load_file.assert_has_calls(expected_calls)
        self.assertEqual(sorted(['/dev/vda', '/dev/vdb']), sorted(devs))

    @patch('curtin.block.get_blockdev_for_partition')
    @patch('curtin.block.mdadm.os.path.exists')
    def tests_md_get_devices_list_nomd(self, mock_exists, mock_getbdev):
        mdname = '/dev/md0'
        mock_exists.return_value = False
        mock_getbdev.return_value = ('md0', None)
        with self.assertRaises(OSError):
            mdadm.md_get_devices_list(mdname)

    @patch('curtin.block.mdadm.os')
    def test_md_check_array_uuid(self, mock_os):
        devname = '/dev/md0'
        md_uuid = '93a73e10:427f280b:b7076c02:204b8f7a'
        mock_os.path.realpath.return_value = devname
        rv = mdadm.md_check_array_uuid(devname, md_uuid)
        self.assertTrue(rv)

    @patch('curtin.block.mdadm.os')
    def test_md_check_array_uuid_mismatch(self, mock_os):
        devname = '/dev/md0'
        md_uuid = '93a73e10:427f280b:b7076c02:204b8f7a'
        mock_os.path.realpath.return_value = '/dev/md1'

        with self.assertRaises(ValueError):
            mdadm.md_check_array_uuid(devname, md_uuid)

    @patch('curtin.block.mdadm.mdadm_query_detail')
    def test_md_get_uuid(self, mock_query):
        mdname = '/dev/md0'
        md_uuid = '93a73e10:427f280b:b7076c02:204b8f7a'
        mock_query.return_value = {'MD_UUID': md_uuid}
        uuid = mdadm.md_get_uuid(mdname)
        self.assertEqual(md_uuid, uuid)

    @patch('curtin.block.mdadm.mdadm_query_detail')
    def test_md_get_uuid_dev_none(self, mock_query):
        mdname = None
        with self.assertRaises(ValueError):
            mdadm.md_get_uuid(mdname)

    def test_md_check_raid_level(self):
        for rl in mdadm.VALID_RAID_LEVELS:
            self.assertTrue(mdadm.md_check_raidlevel(rl))

    def test_md_check_raid_level_bad(self):
        bogus = '27'
        self.assertTrue(bogus not in mdadm.VALID_RAID_LEVELS)
        with self.assertRaises(ValueError):
            mdadm.md_check_raidlevel(bogus)

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.side_effect = [
            'clean',  # array_state
            '0',  # degraded
            'idle',  # sync_action
        ]
        self.assertTrue(mdadm.md_check_array_state(mdname))

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_norw(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.side_effect = [
            'suspended',  # array_state
            '0',  # degraded
            'idle',  # sync_action
        ]
        with self.assertRaises(ValueError):
            mdadm.md_check_array_state(mdname)

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_degraded(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.side_effect = [
            'clean',  # array_state
            '1',  # degraded
            'idle',  # sync_action
        ]
        with self.assertRaises(ValueError):
            mdadm.md_check_array_state(mdname)

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_degraded_empty(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.side_effect = [
            'clean',  # array_state
            '',  # unknown
            'idle',  # sync_action
        ]
        with self.assertRaises(ValueError):
            mdadm.md_check_array_state(mdname)

    @patch('curtin.block.mdadm.md_sysfs_attr')
    def test_md_check_array_state_sync(self, mock_attr):
        mdname = '/dev/md0'
        mock_attr.side_effect = [
            'clean',  # array_state
            '0',  # degraded
            'recovery',  # sync_action
        ]
        with self.assertRaises(ValueError):
            mdadm.md_check_array_state(mdname)

    @patch('curtin.block.mdadm.md_check_array_uuid')
    @patch('curtin.block.mdadm.md_get_uuid')
    def test_md_check_uuid(self, mock_guuid, mock_ckuuid):
        mdname = '/dev/md0'
        mock_guuid.return_value = '93a73e10:427f280b:b7076c02:204b8f7a'
        mock_ckuuid.return_value = True

        rv = mdadm.md_check_uuid(mdname)
        self.assertTrue(rv)

    @patch('curtin.block.mdadm.md_check_array_uuid')
    @patch('curtin.block.mdadm.md_get_uuid')
    def test_md_check_uuid_nouuid(self, mock_guuid, mock_ckuuid):
        mdname = '/dev/md0'
        mock_guuid.return_value = None
        with self.assertRaises(ValueError):
            mdadm.md_check_uuid(mdname)

    @patch('curtin.block.mdadm.md_get_devices_list')
    def test_md_check_devices(self, mock_devlist):
        mdname = '/dev/md0'
        devices = ['/dev/vdc', '/dev/vdd']

        mock_devlist.return_value = devices
        rv = mdadm.md_check_devices(mdname, devices)
        self.assertEqual(rv, None)

    @patch('curtin.block.mdadm.md_get_devices_list')
    def test_md_check_devices_wrong_devs(self, mock_devlist):
        mdname = '/dev/md0'
        devices = ['/dev/vdc', '/dev/vdd']

        mock_devlist.return_value = ['/dev/sda']
        with self.assertRaises(ValueError):
            mdadm.md_check_devices(mdname, devices)

    def test_md_check_devices_no_devs(self):
        mdname = '/dev/md0'
        devices = []

        with self.assertRaises(ValueError):
            mdadm.md_check_devices(mdname, devices)

    @patch('curtin.block.mdadm.md_get_spares_list')
    def test_md_check_spares(self, mock_devlist):
        mdname = '/dev/md0'
        spares = ['/dev/vdc', '/dev/vdd']

        mock_devlist.return_value = spares
        rv = mdadm.md_check_spares(mdname, spares)
        self.assertEqual(rv, None)

    @patch('curtin.block.mdadm.md_get_spares_list')
    def test_md_check_spares_wrong_devs(self, mock_devlist):
        mdname = '/dev/md0'
        spares = ['/dev/vdc', '/dev/vdd']

        mock_devlist.return_value = ['/dev/sda']
        with self.assertRaises(ValueError):
            mdadm.md_check_spares(mdname, spares)

    @patch('curtin.block.mdadm.mdadm_examine')
    @patch('curtin.block.mdadm.mdadm_query_detail')
    @patch('curtin.block.mdadm.md_get_uuid')
    def test_md_check_array_membership(self, mock_uuid, mock_query,
                                       mock_examine):
        mdname = '/dev/md0'
        devices = ['/dev/vda', '/dev/vdb', '/dev/vdc', '/dev/vdd']
        md_uuid = '93a73e10:427f280b:b7076c02:204b8f7a'
        md_dict = {'MD_UUID': md_uuid}
        mock_query.return_value = md_dict
        mock_uuid.return_value = md_uuid
        mock_examine.side_effect = [md_dict] * len(devices)
        expected_calls = []
        for dev in devices:
            expected_calls.append(call(dev, export=False))

        rv = mdadm.md_check_array_membership(mdname, devices)

        self.assertEqual(rv, None)
        mock_uuid.assert_has_calls([call(mdname)])
        mock_examine.assert_has_calls(expected_calls)

    @patch('curtin.block.mdadm.mdadm_examine')
    @patch('curtin.block.mdadm.mdadm_query_detail')
    @patch('curtin.block.mdadm.md_get_uuid')
    def test_md_check_array_membership_bad_dev(self, mock_uuid, mock_query,
                                               mock_examine):
        mdname = '/dev/md0'
        devices = ['/dev/vda', '/dev/vdb', '/dev/vdc', '/dev/vdd']
        md_uuid = '93a73e10:427f280b:b7076c02:204b8f7a'
        md_dict = {'MD_UUID': md_uuid}
        mock_query.return_value = md_dict
        mock_uuid.return_value = md_uuid
        mock_examine.side_effect = [
            md_dict,
            {},
            md_dict,
            md_dict,
        ]  # one device isn't a member

        with self.assertRaises(ValueError):
            mdadm.md_check_array_membership(mdname, devices)

    @patch('curtin.block.mdadm.mdadm_examine')
    @patch('curtin.block.mdadm.mdadm_query_detail')
    @patch('curtin.block.mdadm.md_get_uuid')
    def test_md_check_array_membership_wrong_array(self, mock_uuid, mock_query,
                                                   mock_examine):
        mdname = '/dev/md0'
        devices = ['/dev/vda', '/dev/vdb', '/dev/vdc', '/dev/vdd']
        md_uuid = '93a73e10:427f280b:b7076c02:204b8f7a'
        md_dict = {'MD_UUID': '11111111:427f280b:b7076c02:204b8f7a'}
        mock_query.return_value = md_dict
        mock_uuid.return_value = md_uuid
        mock_examine.side_effect = [md_dict] * len(devices)

        with self.assertRaises(ValueError):
            mdadm.md_check_array_membership(mdname, devices)

    @patch('curtin.block.mdadm.md_check_array_membership')
    @patch('curtin.block.mdadm.md_check_spares')
    @patch('curtin.block.mdadm.md_check_devices')
    @patch('curtin.block.mdadm.md_check_uuid')
    @patch('curtin.block.mdadm.md_check_raidlevel')
    @patch('curtin.block.mdadm.md_check_array_state')
    def test_md_check_all_good(self, mock_array, mock_raid, mock_uuid,
                               mock_dev, mock_spare, mock_member):
        md_devname = '/dev/md0'
        raidlevel = 1
        devices = ['/dev/vda', '/dev/vdb']
        spares = ['/dev/vdc']

        mock_array.return_value = None
        mock_raid.return_value = None
        mock_uuid.return_value = None
        mock_dev.return_value = None
        mock_spare.return_value = None
        mock_member.return_value = None

        mdadm.md_check(md_devname, raidlevel, devices=devices, spares=spares)

        mock_array.assert_has_calls([call(md_devname)])
        mock_raid.assert_has_calls([call(raidlevel)])
        mock_uuid.assert_has_calls([call(md_devname)])
        mock_dev.assert_has_calls([call(md_devname, devices)])
        mock_spare.assert_has_calls([call(md_devname, spares)])
        mock_member.assert_has_calls([call(md_devname, devices + spares)])

    def test_md_check_all_good_devshort(self):
        md_devname = 'md0'
        raidlevel = 1
        devices = ['/dev/vda', '/dev/vdb']
        spares = ['/dev/vdc']

        with self.assertRaises(ValueError):
            mdadm.md_check(md_devname, raidlevel, devices=devices,
                           spares=spares)

    def test_md_present(self):
        mdname = 'md0'
        self.mock_util.load_file.return_value = textwrap.dedent("""
        Personalities : [raid1] [linear] [multipath] [raid0] [raid6] [raid5]
        [raid4] [raid10]
        md0 : active raid1 vdc1[1] vda2[0]
              3143680 blocks super 1.2 [2/2] [UU]

        unused devices: <none>
        """)

        md_is_present = mdadm.md_present(mdname)

        self.assertTrue(md_is_present)
        self.mock_util.load_file.assert_called_with('/proc/mdstat')

    def test_md_present_not_found(self):
        mdname = 'md1'
        self.mock_util.load_file.return_value = textwrap.dedent("""
        Personalities : [raid1] [linear] [multipath] [raid0] [raid6] [raid5]
        [raid4] [raid10]
        md0 : active raid1 vdc1[1] vda2[0]
              3143680 blocks super 1.2 [2/2] [UU]

        unused devices: <none>
        """)

        md_is_present = mdadm.md_present(mdname)

        self.assertFalse(md_is_present)
        self.mock_util.load_file.assert_called_with('/proc/mdstat')

    def test_md_present_not_found_check_matching(self):
        mdname = 'md1'
        found_mdname = 'md10'
        self.mock_util.load_file.return_value = textwrap.dedent("""
        Personalities : [raid1] [linear] [multipath] [raid0] [raid6] [raid5]
        [raid4] [raid10]
        md10 : active raid1 vdc1[1] vda2[0]
               3143680 blocks super 1.2 [2/2] [UU]

        unused devices: <none>
        """)

        md_is_present = mdadm.md_present(mdname)

        self.assertFalse(md_is_present,
                         "%s mistakenly matched %s" % (mdname, found_mdname))
        self.mock_util.load_file.assert_called_with('/proc/mdstat')

    def test_md_present_with_dev_path(self):
        mdname = '/dev/md0'
        self.mock_util.load_file.return_value = textwrap.dedent("""
        Personalities : [raid1] [linear] [multipath] [raid0] [raid6] [raid5]
        [raid4] [raid10]
        md0 : active raid1 vdc1[1] vda2[0]
              3143680 blocks super 1.2 [2/2] [UU]

        unused devices: <none>
        """)

        md_is_present = mdadm.md_present(mdname)

        self.assertTrue(md_is_present)
        self.mock_util.load_file.assert_called_with('/proc/mdstat')

    def test_md_present_none(self):
        mdname = ''
        self.mock_util.load_file.return_value = textwrap.dedent("""
        Personalities : [raid1] [linear] [multipath] [raid0] [raid6] [raid5]
        [raid4] [raid10]
        md0 : active raid1 vdc1[1] vda2[0]
              3143680 blocks super 1.2 [2/2] [UU]

        unused devices: <none>
        """)

        with self.assertRaises(ValueError):
            mdadm.md_present(mdname)

        # util.load_file should NOT have been called
        self.assertEqual([], self.mock_util.call_args_list)

    def test_md_present_no_proc_mdstat(self):
        mdname = 'md0'
        self.mock_util.side_effect = IOError

        md_is_present = mdadm.md_present(mdname)
        self.assertFalse(md_is_present)
        self.mock_util.load_file.assert_called_with('/proc/mdstat')


# vi: ts=4 expandtab syntax=python
