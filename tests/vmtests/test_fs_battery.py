# This file is part of curtin. See LICENSE file for copyright and license info.

from . import VMBaseClass, skip_if_flag
from .releases import base_vm_classes as relbase
from .releases import centos_base_vm_classes as centos_relbase

from curtin import config

import os
import textwrap


def _parse_blkid_output(content):
    """Parse the output of the 'blkid' calls in collect_script.

    Input is groups of lines.  Each line is key=value. Each group
    has the first line with key DEVNAME and last line key RESULT.

    returned value is a dictionary by shortened devname like:.
    {'part1': {'devname': 'part1', 'label': '...'}}"""
    def _record(lines):
        record = {}
        for line in lines:
            key, _, val = line.partition("=")
            if key == 'DEVNAME':
                bname = os.path.basename(val)
                # bname is 'virtio-fsbattery-partX'. get just 'partX'
                record[key.lower()] = bname.rpartition("-")[2]
            elif key in ('RESULT', 'LABEL', 'UUID', 'TYPE'):
                record[key.lower()] = val
        return record

    lines = []
    records = {}
    for line in content.splitlines():
        lines.append(line)
        if line.startswith("RESULT"):
            r = _record(lines)
            records[r['devname']] = r
            lines = []

    return records


class TestFsBattery(VMBaseClass):
    interactive = False
    test_type = 'storage'
    conf_file = "examples/tests/filesystem_battery.yaml"
    extra_disks = ['20G']
    extra_collect_scripts = [textwrap.dedent("""
        cd OUTPUT_COLLECT_D
        cat /proc/1/mountinfo > mountinfo

        for p in /my/bind-over-var-cache/man /my/bind-ro-etc/passwd; do
            [ -e "$p" ] && echo "$p: present" || echo "$p: missing"
        done > my-path-checks

        set +x
        serial="fsbattery"
        disk=$(echo /dev/disk/by-id/*-$serial)
        [ -b "$disk" ] || { echo "No disk with serial $serial." exit 1; }

        # not all blkid versions output DEVNAME, so do it ourselves.
        blkid -o export "$disk" | grep -q DEVNAME= &&
           hasdev=true || hasdev=false
        for d in $disk-part*; do
            $hasdev || echo DEVNAME=$d
            blkid -o export "$d"
            echo RESULT=$?
        done > battery-blkid

        mpbase=/tmp/mp;
        mkdir -p /tmp/mp
        for d in $disk-part*; do
            fstype=$(blkid -o export "$d" |
                     awk -F= '$1 == "TYPE" { print $2 }')
            if [ -z "$fstype" ]; then
                msg="FAIL: blkid did not identify fstype"
            else
                mp="$mpbase/${d##*-}"
                mkdir "$mp"
                echo "${d##*-} $fstype" > "$mp.info"
                if out=$(mount -t "$fstype" "$d" "$mp" 2>&1); then
                    msg="PASS"
                else
                    rm -Rf "$mp.info" "$mp"
                    msg="FAIL: mount $fstype failed $?: $out"
                fi
            fi
            echo "${d##*-} mount: $msg"
        done > battery-mount-umount

        awk '$5 ~ mp { print $0 }' "mp=$mpbase/" \
            /proc/1/mountinfo > battery-mountinfo

        for info in $mpbase/*.info; do
            read part fstype < "$info"
            mp="${info%.info}"
            out=$(umount "$mp" 2>&1) &&
                echo "$part umount: PASS" ||
                echo "$part umount: FAIL: $out"
        done >> battery-mount-umount

        # collect ext4 features on myext4 partition
        dumpe2fs /dev/disk/by-label/myext4 > myext4.dump

        exit 0
        """)]

    def get_fs_entries(self):
        """Return a dictionary of fs entires in config by 'partX'."""
        stgcfg = config.load_config(self.conf_file)['storage']['config']
        fs_entries = {}
        for entry in stgcfg:
            if not entry['id'].startswith("fs"):
                continue
            part = "part%d" % int(entry['id'][2:])
            fs_entries[part] = entry.copy()
        return fs_entries

    @skip_if_flag('expected_failure')
    def test_blkid_output(self):
        """Check the recorded output of 'blkid -o export' on each partition.

        parse parse the 'battery-blkid' collected file, and compare it
        to expected output from reading the storage config."""
        results = _parse_blkid_output(self.load_collect_file("battery-blkid"))

        # tools for these types do not support providing uuid.
        no_uuid_types = ['vfat', 'jfs', 'fat16', 'fat32', 'ntfs']

        for k, v in results.items():
            if v['type'] in no_uuid_types:
                del v['uuid']

        # these curtin "types" show in blkid output differently.
        type2blkid = {'fat32': 'vfat', 'fat16': 'vfat'}
        expected = {}
        for part, entry in self.get_fs_entries().items():
            record = {
                'devname': part,
                'label': entry['label'],
                'type': type2blkid.get(entry['fstype'], entry['fstype']),
                'result': "0",
            }
            if 'uuid' in entry and record['type'] not in no_uuid_types:
                record['uuid'] = entry['uuid']
            expected[record['devname']] = record

        self.assertEqual(expected, results)

    @skip_if_flag('expected_failure')
    def test_mount_umount(self):
        """Check output of mount and unmount operations for each fs."""
        results = self.load_collect_file("battery-mount-umount").splitlines()
        entries = self.get_fs_entries()
        expected = (["%s mount: PASS" % k for k in entries] +
                    ["%s umount: PASS" % k for k in entries])
        self.assertEqual(sorted(expected), sorted(results))

    @skip_if_flag('expected_failure')
    def test_fstab_has_mounts(self):
        """Verify each of the expected "my" mounts got into fstab."""
        expected = [
            "none /my/tmpfs tmpfs size=4194304 0 1".split(),
            "none /my/ramfs ramfs defaults 0 0".split(),
            "/my/bind-over-var-cache /var/cache none bind 3 0".split(),
            "/etc /my/bind-ro-etc none bind,ro 1 0".split(),
        ]
        fstab_found = [
            line.split() for line in self.load_collect_file(
                "fstab").splitlines()]
        self.assertEqual(expected, [e for e in expected if e in fstab_found])

    @skip_if_flag('expected_failure')
    def test_mountinfo_has_mounts(self):
        """Verify the my mounts got into mountinfo.

        This is a light check that things got mounted.  We do not check
        options as to not break on different kernel behavior.
        Maybe it could/should."""
        # mountinfo has src and path as 4th and 5th field.
        data = self.load_collect_file("mountinfo").splitlines()
        dest_src = {}
        for line in data:
            toks = line.split()
            if not (toks[3].startswith("/my/") or toks[4].startswith("/my/")):
                continue
            dest_src[toks[4]] = toks[3]
        self.assertTrue("/my/ramfs" in dest_src)
        self.assertTrue("/my/tmpfs" in dest_src)
        self.assertEqual(dest_src.get("/var/cache"), "/my/bind-over-var-cache")
        self.assertEqual(dest_src.get("/my/bind-ro-etc"), "/etc")

    @skip_if_flag('expected_failure')
    def test_expected_files_from_bind_mounts(self):
        data = self.load_collect_file("my-path-checks")
        # this file is <path>: (present|missing)
        paths = {}
        for line in data.splitlines():
            path, _, val = line.partition(":")
            paths[path] = val.strip()

        self.assertEqual(
            {'/my/bind-over-var-cache/man': 'present',
             '/my/bind-ro-etc/passwd': 'present'}, paths)

    @skip_if_flag('expected_failure')
    def test_ext4_extra_parameters_used_with_mkfs(self):
        data = self.load_collect_file("myext4.dump")
        self.assertNotIn("ext_attr", data)


class Centos70XenialTestFsBattery(centos_relbase.centos70_xenial,
                                  TestFsBattery):
    __test__ = True

    def test_mount_umount(self):
        """Check output of mount and unmount operations for each fs."""
        # centos does not support: jfs, ntfs, reiserfs
        unsupported = ['jfs', 'ntfs', 'reiserfs']
        results = [ent for ent in
                   self.load_collect_file("battery-mount-umount").splitlines()
                   if ent.split()[-1].replace("'", "") not in unsupported]
        entries = {k: v for k, v in self.get_fs_entries().items()
                   if v['fstype'] not in unsupported}
        expected = (["%s mount: PASS" % k for k in entries] +
                    ["%s umount: PASS" % k for k in entries])
        self.assertEqual(sorted(expected), sorted(results))


class XenialGATestFsBattery(relbase.xenial_ga, TestFsBattery):
    __test__ = True


class XenialHWETestFsBattery(relbase.xenial_hwe, TestFsBattery):
    __test__ = True


class XenialEdgeTestFsBattery(relbase.xenial_edge, TestFsBattery):
    __test__ = True


class BionicTestFsBattery(relbase.bionic, TestFsBattery):
    __test__ = True


class FocalTestFsBattery(relbase.focal, TestFsBattery):
    skip = True  # XXX Broken for now
    __test__ = True


class JammyTestFsBattery(relbase.jammy, TestFsBattery):
    skip = True  # XXX Broken for now
    __test__ = True


# vi: ts=4 expandtab syntax=python
