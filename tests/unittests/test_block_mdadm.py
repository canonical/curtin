from unittest import TestCase
from mock import call, patch
from curtin.block import mdadm
import subprocess


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

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'precise'}
        self.mock_util.subp.side_effect = [
            ("", ""),  # mdadm assemble
            ("", ""),  # udevadm settle
        ]

    def test_mdadm_assemble_scan(self):
        mdadm.mdadm_assemble(scan=True)
        expected_calls = [
            call(["mdadm", "--assemble", "--scan"], capture=True),
            call(["udevadm", "settle"]),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)

    def test_mdadm_assemble_md_devname(self):
        md_devname = "/dev/md0"
        mdadm.mdadm_assemble(md_devname=md_devname)

        expected_calls = [
            call(["mdadm", "--assemble", md_devname, "--run"], capture=True),
            call(["udevadm", "settle"]),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)

    def test_mdadm_assemble_md_devname_short(self):
        md_devname = "md0"
        mdadm.mdadm_assemble(md_devname=md_devname)

        expected_calls = [
            call(["mdadm", "--assemble", "/dev/md0", "--run"], capture=True),
            call(["udevadm", "settle"]),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)

    def test_mdadm_assemble_md_devname_none(self):
        with self.assertRaises(ValueError):
            md_devname = None
            mdadm.mdadm_assemble(md_devname=md_devname)

    def test_mdadm_assemble_md_devname_devices(self):
        md_devname = "/dev/md0"
        devices = ["/dev/vdc1", "/dev/vdd1"]
        mdadm.mdadm_assemble(md_devname=md_devname, devices=devices)
        expected_calls = [
            call(["mdadm", "--assemble", md_devname, "--run"] + devices,
                 capture=True),
            call(["udevadm", "settle"]),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)


class TestBlockMdadmCreate(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmCreate, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'precise'}

    def prepare_mock(self, md_devname, raidlevel, devices, spares):
        side_effects = []
        expected_calls = []

        # don't mock anything if raidlevel and spares mismatch
        if spares and raidlevel not in mdadm.SPARE_RAID_LEVELS:
            return (side_effects, expected_calls)

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
               "--level=%s" % raidlevel, "--raid-devices=%s" % len(devices)] +
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
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'xenial'}
        self.mock_util.subp.side_effect = [
            ("", ""),  # mdadm stop device
        ]

    def test_mdadm_stop_no_devpath(self):
        with self.assertRaises(ValueError):
            mdadm.mdadm_stop(None)

    def test_mdadm_stop(self):
        device = "/dev/vdc"
        mdadm.mdadm_stop(device)
        expected_calls = [
            call(["mdadm", "--stop", device], rcs=[0, 1], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)


class TestBlockMdadmRemove(MdadmTestBase):
    def setUp(self):
        super(TestBlockMdadmRemove, self).setUp()
        self.add_patch('curtin.block.mdadm.util', 'mock_util')
        self.add_patch('curtin.block.mdadm.is_valid_device', 'mock_valid')

        # Common mock settings
        self.mock_valid.return_value = True
        self.mock_util.lsb_release.return_value = {'codename': 'xenial'}
        self.mock_util.subp.side_effect = [
            ("", ""),  # mdadm stop device
        ]

    def test_mdadm_remove_no_devpath(self):
        with self.assertRaises(ValueError):
            mdadm.mdadm_remove(None)

    def test_mdadm_remove(self):
        device = "/dev/vdc"
        mdadm.mdadm_remove(device)
        expected_calls = [
            call(["mdadm", "--remove", device], rcs=[0, 1], capture=True),
        ]
        self.mock_util.subp.assert_has_calls(expected_calls)


# vi: ts=4 expandtab syntax=python
