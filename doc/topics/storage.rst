=======
Storage
=======

Curtin supports a user-configurable storage layout.  This format lets users
(including via MAAS) to customize their machines' storage configuration by
creating partitions, RAIDs, LVMs, formatting with file systems and setting
mount points.

Custom storage configuration is handled by the ``block-meta custom`` command
in curtin. Partitioning layout is read as a list of in-order modifications to
make to achieve the desired configuration. The top level configuration key
containing this configuration is ``storage``. This key should contain a
dictionary with at least a version number and the configuration list. The
current config specification is ``version: 1``.

**Config Example**::

 storage:
   version: 1
   config:
     - id: sda
       type: disk
       ptable: gpt
       serial: QM00002
       model: QEMU_HARDDISK

Configuration Types
-------------------
Each entry in the config list is a dictionary with several keys which vary
between commands. The two dictionary keys that every entry in the list needs
to have are ``id: <id>`` and ``type: <type>``.

An entry's ``id`` allows other entries in the config to refer to a specific
entry. It can be any string other than one with a special meaning in yaml, such
as ``true`` or ``none``.

An entry's ``type`` tells curtin how to handle a particular entry. Available
commands include:

- Disk Command (``disk``)
- Partition Command (``partition``)
- Format Command (``format``)
- Mount Command  (``mount``)
- LVM_VolGroup Command (``lvm_volgroup``)
- LVM_Partition Command (``lvm_partition``)
- DM_Crypt Command (``dm_crypt``)
- RAID Command (``raid``)
- Bcache Command (``bcache``)

Disk Command
~~~~~~~~~~~~
The disk command sets up disks for use by curtin. It can wipe the disks, create
partition tables, or just verify that the disks exist with an existing partition
table. A disk command may contain all or some of the following keys:

**ptable**: *msdos, gpt*

If the ``ptable`` key is present and a valid type of partition table, curtin
will create an empty partition table of that type on the disk.  At the moment,
msdos and gpt partition tables are supported.

**serial**: *<serial number>*

In order to uniquely identify a disk on the system its serial number should be
specified. This ensures that even if additional storage devices
are added to the system during installation, or udev rules cause the path to a
disk to change curtin will still be able to correctly identify the disk it
should be operating on using ``/dev/disk/by-id``.

This is the preferred way to identify a disk and should be used in all
production environments as it is less likely to point to an incorrect device.

**path**: *<path to device with leading /dev*

The ``path`` key can be used to identify the disk.  If both ``serial`` and
``path`` are specified, curtin will use the serial number and ignore the path
that was specified.

iSCSI disks are supported via a special path prefix of 'iscsi:'. If this
prefix is found in the path specification for a disk, it is assumed to
be an iSCSI disk specification and must be in a `RFC4173
<https://tools.ietf.org/html/rfc4173>`_ compliant format, with
extensions from Debian for supporting authentication:

``iscsi:[user:password[:iuser:ipassword]@]host:proto:port:lun:targetname``

- ``user``: User to authenticate with, if needed, for iSCSI initiator
  authentication. Only CHAP authentication is supported at this time.
- ``password``: Password to authenticate with, if needed, for iSCSI
  initiator authentication. Only CHAP authentication is supported at
  this time.
- ``iuser``: User to authenticate with, if needed, for iSCSI target
  authentication. Only CHAP authentication is supported at this time.
- ``ipassword``: Password to authenticate with, if needed, for iSCSI
  target authentication. Only CHAP authentication is supported at this
  time.

.. note::

  Curtin will treat it as an error if the user and password are not both
  specified for initiator and target authentication.

- ``host``: iSCSI server hosting the specified target. It can be a
  hostname, IPv4 or IPv6 address. If specified as an IPv6 address, it
  must be specified as ``[address]``.
- ``proto``: Specifies the protocol used for iSCSI. Currently only
  ``6``, or TCP, is supported and any other value is ignored. If not
  specified, ``6`` is assumed.
- ``port``: Specifies the port the iSCSI server is listening on. If not
  specified, ``3260`` is assumed.
- ``lun``: Specifies the LUN of the iSCSI target to connect to. If not
  specified, ``0`` is assumed.
- ``targetname``: Specifies the iSCSI target to connect to, by its name
  on the iSCSI server.

.. note::

  Curtin will treat it as an error if the host and targetname are not
  specified.

Any iSCSI disks specified will be configured to login at boot in the
target.

**model**: *<disk model>*

This can specify the manufacturer or model of the disk. It is not currently
used by curtin, but can be useful for a human reading a config file. Future
versions of curtin may make use of this information.

**wipe**: *superblock, superblock-recursive, zero, random*

If wipe is specified, **the disk contents will be destroyed**.  In the case that
a disk is a part of virtual block device, like bcache, RAID array, or LVM, then
curtin will attempt to tear down the virtual device to allow access to the disk
for resetting the disk.

The most common option for clearing a disk is  ``wipe: superblock``.  In some
cases use of ``wipe: superblock-recursive`` is useful to ensure that embedded
superblocks on a disk aren't rediscovered during probing.  For example, LVM,
bcache and RAID on a partition would have metadata outside of the range of a
superblock wipe of the start and end sections of the disk.

The ``wipe: zero`` option will write zeros to each sector of the disk.
Depending on the size and speed of the disk; it may take a long time to
complete.

The ``wipe: random`` option will write pseudo-random data from /dev/urandom
Depending on the size and speed of the disk; it may take a long time to
complete.

**preserve**: *true, false*

When the preserve key is present and set to ``true`` curtin will attempt
to use the disk without damaging data present on it. If ``preserve`` is set and
``ptable`` is also set, then curtin will validate that the partition table
specified by ``ptable`` exists on the disk and will raise an error if it does
not. If ``preserve`` is set and ``ptable`` is not, then curtin will be able to
use the disk in later commands, but will not check if the disk has a valid
partition table, and will only verify that the disk exists.

It can be dangerous to try to move or re-size filesystems and partitions
containing data that needs to be preserved. Therefor curtin does not support
preserving a disk without also preserving the partitions on it. If a disk is
set to be preserved and curtin is told to move a partition on that disk,
installation will stop. It is still possible to reformat partitions that do
not need to be preserved.

**name**: *<name>*

If the ``name`` key is present, curtin will create a udev rule that makes a
symbolic link to the disk with the given name value. This makes it easy to find
disks on an installed system. The links are created in
``/dev/disk/by-dname/<name>``.
A link to each partition on the disk will also be created at
``/dev/disk/by-dname/<name>-part<number>``, so if ``name: maindisk`` is set,
the disk will be at ``/dev/disk/by-dname/maindisk`` and the first partition on
it will be at ``/dev/disk/by-dname/maindisk-part1``.

**grub_device**: *true, false*

If the ``grub_device`` key is present and set to true, then when post
installation hooks are run grub will be installed onto this disk. In most
situations it is not necessary to specify this value as curtin will detect
and determine which device to use as a boot disk.  In cases where the boot
device is on a special volume, such as a RAID array or a LVM Logical Volume,
it may be necessary to specify the device that will hold the grub bootloader.

**Config Example**::

 - id: disk0
   type: disk
   ptable: gpt
   serial: QM00002
   model: QEMU_HARDDISK
   name: maindisk
   wipe: superblock

Partition Command
~~~~~~~~~~~~~~~~~
The partition command creates a single partition on a disk. Curtin only needs
to be told which disk to use and the size of the partition.  Additional options
are available.

**number**: *<number>*

The partition number can be specified using ``number``. However, numbers must
be in order and some situations, such as extended/logical partitions on msdos
partition tables will require special numbering, so it maybe better to omit 
the partition number. If the ``number`` key is not present, curtin will attempt
determine the right number to use.

**size**: *<size>*

The partition size can be specified with the ``size`` key. Sizes must be
given with an appropriate SI unit, such as *B, kB, MB, GB, TB*, or using just
the appropriate SI prefix, i.e. *B, k, M, G, T...*

.. note::

  Curtin does not adjust size values.  If you specific a size that exceeds the 
  capacity of a device then installation will fail.

**device**: *<device id>*

The ``device`` key refers to the ``id`` of a disk in the storage configuration.
The disk entry must already be defined in the list of commands to ensure that
it has already been processed.

**wipe**: *superblock, pvremove, zero, random*

After the partition is added to the disk's partition table, curtin can run a
wipe command on the partition. The wipe command values are the sames as for
disks.

**flag**: *logical, extended, boot, bios_grub, swap, lvm, raid, home, prep*

If the ``flag`` key is present, curtin will set the specified flag on the
partition. Note that some flags only apply to msdos partition tables, and some
only apply to gpt partition tables.

The *logical/extended* partition flags can be used to create logical partitions
on a msdos table. An extended partition should be created containing all of the
empty space on the drive, and logical partitions can be created within it. A
extended partition must already be present to create logical partitions. If the
``number`` flag is set for an extended partition it must be set to 4, and
each logical partition should be numbered starting from 5.

On msdos partition tables, the *boot* flag sets the boot parameter to that
partition. On gpt partition tables, the boot flag sets the esp flag on the
partition.

If the host system for curtin has been booted using UEFI then curtin will
install grub to the esp partition. If the system installation media
has been booted using an MBR, grub will be installed onto the disk's MBR.
However, on a disk with a gpt partition table, there is not enough space after
the MBR for grub to store its second stage core.img, so a small un-formatted
partition with the *bios_grub* flag is needed. This partition should be placed
at the beginning of the disk and should be 1MB in size. It should not contain a
filesystem or be mounted anywhere on the system.

**preserve**: *true, false*

If the preserve flag is set to true, curtin will verify that the partition
exists and will not modify the partition.

**Config Example**::

 - id: disk0-part1
   type: partition
   number: 1
   size: 8GB
   device: disk0
   flag: boot

Format Command
~~~~~~~~~~~~~~
The format command makes filesystems on a volume. The filesystem type and
target volume can be specified, as well as a few other options.

**fstype**: ext4, ext3, fat32, fat16, swap, xfs

The ``fstype`` key specifies what type of filesystem format curtin should use
for this volume. Curtin knows about common Linux filesystems such as ext4/3 and
fat filesystems and makes use of additional parameters and flags to optimize the
filesystem.  If the ``fstype`` value is not known to curtin, that is not fatal.
Curtin will check if ``mkfs.<fstype>`` exists and if so,  will use that tool to
format the target volume.

For fat filesystems, the size of the fat table can be specified by entering
*fat64*, *fat32*, *fat16*, or *fat12* instead of just entering *fat*.
If *fat* is used, then ``mkfs.fat`` will automatically determine the best
size fat table to use, probably *fat32*.

If ``fstype: swap`` is set, curtin will create a swap partition on the target
volume.

**volume**: *<volume id>*

The ``volume`` key refers to the ``id`` of the target volume in the storage
config.  The target volume must already exist and be accessible. Any type
of target volume can be used as long as it has a block device that curtin
can locate.

**label**: *<volume name>*

The ``label`` key tells curtin to create a filesystem LABEL when formatting a
volume. Note that not all filesystem types support names and that there are
length limits for names. For fat filesystems, names are limited to 11
characters. For ext4/3 filesystems, names are limited to 16 characters.

If curtin does not know about the filesystem type it is using, then the
``label`` key will be ignored, because curtin will not know the correct flags
to set the label value in the filesystem metadata.

**uuid**: *<uuid>*

If the ``uuid`` key is set and ``fstype`` is set to *ext4* or *ext3*, then
curtin will set the uuid of the new filesystem to the specified value.

**preserve**: *true, false*

If the ``preserve`` key is set to true, curtin will not format the partition.

**Config Example**::

 - id: disk0-part1-fs1
   type: format
   fstype: ext4
   label: cloud-image
   volume: disk0-part1

Mount Command
~~~~~~~~~~~~~
The mount command mounts the target filesystem and creates an entry for it in
the newly installed system's ``/etc/fstab``. The path to the target mountpoint
must be specified as well as the target filesystem.

**path**: *<path>*

The ``path`` key tells curtin where the filesystem should be mounted on the
target system. An entry in the target system's ``/etc/fstab`` will be created
for the target device which will mount it in the correct place once the
installed system boots.

If the device specified is formatted as swap space, then an entry will be added
to the target system's ``/etc/fstab`` to make use of this swap space.

When entries are created in ``/etc/fstab``, curtin will use the most reliable
method available to identify each device. For regular partitions, curtin will
use the UUID of the filesystem present on the partition. For special devices,
such as RAID arrays, or LVM logical volumes, curtin will use their normal path
in ``/dev``.

**device**: *<device id>*

The ``device`` key refers to the ``id`` of the target device in the storage
config. The target device must already contain a valid filesystem and be
accessible.

.. note::

  If the specified device refers to an iSCSI device, the corresponding
  fstab entry will contain ``_netdev`` to indicate networking is
  required to mount this filesystem.

**Config Example**::

 - id: disk0-part1-fs1-mount0
   type: mount
   path: /home
   device: disk0-part1-fs1

Lvm Volgroup Command
~~~~~~~~~~~~~~~~~~~~
The lvm_volgroup command creates LVM Physical Volumes (PV) and connects them in
a LVM Volume Group (vg). The command requires a name for the volgroup and a
list of the devices that should be used as physical volumes.

**name**: *<name>*

The ``name`` key specifies the name of the volume group.  It anything can be
used except words with special meanings in YAML, such as *true*, or *none*.

**devices**: *[]*

The ``devices`` key gives a list of devices to use as physical volumes. Each
device is specified using the ``id`` of existing devices in the storage config.
Almost anything can be used as a device such as partitions, whole disks, RAID.

**Config Example**::

 - id: volgroup1
   type: lvm_volgroup
   name: vg1
   devices:
     - disk0-part2
     - disk1

Lvm Partition Command
~~~~~~~~~~~~~~~~~~~~~
The lvm_partition command creates a lvm logical volume on the specified
volgroup with the specified size. It also assigns it the specified name.

**name**: *<name>*

The ``name`` key specifies the name of the Logical Volume (LV) to be created.

Curtin creates udev rules for Logical Volumes to give them consistently named 
symbolic links in the target system under ``/dev/disk/by-dname/``. The naming
scheme for Logical Volumes follows the pattern
``<volgroup name>-<logical volume name>``.  For example a ``lvm_partition``
with ``name`` *lv1* on a ``lvm_volgroup`` named *vg1* would have the path
``/dev/disk/by-dname/vg1-lv1``.

**volgroup**: *<volgroup id>*

The ``volgroup`` key specifies the ``id`` of the Volume Group in which to
create the logical volume. The volgroup must already have been created and must
have enough free space on it to create the logical volume.  The volgroup should
be specified using the ``id`` key of the volgroup in the storage config, not the
name of the volgroup.

**size**: *<size>*

The ``size`` key tells curtin what size to make the logical volume. The size
can be entered in any format that can be processed by the lvm2 tools, so a
number followed by a SI unit should work, i.e. *B, kB, MB, GB, TB*.

If the ``size`` key is omitted then all remaining space on the volgroup will be
used for the logical volume.

.. note::

  Curtin does not adjust size values.  If you specific a size that exceeds the 
  capacity of a device then installation will fail.


**Config Example**::

 - id: lvm_partition_1
   type: lvm_partition
   name: lv1
   volgroup: volgroup1
   size: 10G


**Combined Example**::

 - id: volgroup1
   type: lvm_volgroup
   name: vg1
   devices:
     - disk0-part2
     - disk1
 - id: lvm_partition_1
   type: lvm_partition
   name: lv1
   volgroup: volgroup1
   size: 10G



Dm-Crypt Command
~~~~~~~~~~~~~~~~
The dm_crypt command creates encrypted volumes using ``cryptsetup``. It
requires a name for the encrypted volume, the volume to be encrypted and a key.
Note that this should not be used for systems where security is a requirement.
The key is stored in plain-text in the storage configuration and it could be
possible for the storage configuration to be intercepted between the utility
that generates it and curtin.

**volume**: *<volume id>*

The ``volume`` key gives the volume that is to be encrypted.

**dm_name**: *<name>*

The ``name`` key specifies the name of the encrypted volume.

**key**: *<key>*

The ``key`` key specifies the password of the encryption key.  The target
system will prompt for this password in order to mount the disk.

.. note::

  Encrypted disks and partitions are tracked in ``/etc/crypttab`` and will  be
  mounted at boot time.

**Config Example**::

 - id: lvm_partition_1
   type: dm_crypt
   dm_name: crypto
   volume: sdb1
   key: testkey

RAID Command
~~~~~~~~~~~~
The RAID command configures Linux Software RAID using mdadm. It needs to be given
a name for the md device, a list of volumes for to compose the md device, an
optional list of devices to be used as spare volumes, and RAID level.

**name**: *<name>*

The ``name`` key specifies the name of the md device.

.. note::

  Curtin creates a udev rule to create a link to the md device in
  ``/dev/disk/by-dname/<name>`` using the specified name.

**raidlevel**: *0, 1, 5, 6, 10*

The ``raidlevel`` key specifies the raid level of the array.

**devices**: *[]*

The ``devices`` key specifies a list of the devices that will be used for the
raid array. Each device must be referenced by ``id`` and the device must be
previously defined in the storage configuration.  Must not be empty.

Devices can either be full disks or partition.


**spare_devices**: *[]*

The ``spare_devices`` key specifies a list of the devices that will be used for
spares in the raid array. Each device must be referenced by ``id`` and the
device must be previously defined in the storage configuration.  May be empty.


**Config Example**::

 - id: raid_array
   type: raid
   name: md0
   raidlevel: 1
   devices:
     - sdb
     - sdc
   spare_devices:
     - sdd

Bcache Command
~~~~~~~~~~~~~~
The bcache command will configure a block-cache device using the Linux kernel
bcache module.  Bcache allows users to use a typically small, but fast SSD or
NVME device as a cache for larger, slower spinning disks.

The bcache command needs to be told which device to use hold the data and which
device to use as its cache device.  A cache device may be reused with multiple
backing devices.


**backing_device**: *<device id>*

The ``backing_device`` key specifies the item in storage configuration to use
as the backing device. This can be any device that would normally be used with
a filesystem on it, such as a partition or a raid array.

**cache_device**: *<device id>*

The ``cache_device`` key specifies the item in the storage configuration to use
as the cache device. This can be a partition or a whole disk. It should be on a
ssd in most cases, as bcache is designed around the performance characteristics
of a ssd.

**cache_mode**: *writethrough, writeback, writearound, none*

The ``cache_mode`` key specifies the mode in which bcache operates.  The
default mode is writethrough which ensures data hits the backing device
before completing the operation.  writeback mode will have higher performance
but exposes dataloss if the cache device fails.  writearound will avoid using
the cache for large sequential writes; useful for not evicting smaller
reads/writes from the cache.  None effectively disables bcache.

**name**: *<name>*

If the ``name`` key is present, curtin will create a link to the device at
``/dev/disk/by-dname/<name>``.

**Config Example**::

 - id: bcache0
   type: bcache
   name: cached_raid
   backing_device: raid_array
   cache_device: sdb


Additional Examples
-------------------

Learn by examples.

- Basic
- LVM
- Bcache
- RAID Boot
- RAID5 + Bcache

Basic Layout
~~~~~~~~~~~~

::

  storage:
    version: 1
    config:
      - id: disk0
        type: disk
        ptable: msdos
        model: QEMU HARDDISK
        path: /dev/vdb
        name: main_disk
        wipe: superblock
        grub_device: true
      - id: disk0-part1
        type: partition
        number: 1
        size: 3GB
        device: disk0
        flag: boot
      - id: disk0-part2
        type: partition
        number: 2
        size: 1GB
        device: disk0
      - id: disk0-part1-format-root
        type: format
        fstype: ext4
        volume: disk0-part1
      - id: disk0-part2-format-home
        type: format
        fstype: ext4
        volume: disk0-part2
      - id: disk0-part1-mount-root
        type: mount
        path: /
        device: disk0-part1-format-root
      - id: disk0-part2-mount-home
        type: mount
        path: /home
        device: disk0-part2-format-home

LVM
~~~

::

  storage:
    version: 1
    config:
      - id: sda
        type: disk
        ptable: msdos
        model: QEMU HARDDISK
        path: /dev/vdb
        name: main_disk
      - id: sda1
        type: partition
        size: 3GB
        device: sda
        flag: boot
      - id: sda_extended
        type: partition
        size: 5G
        flag: extended
        device: sda
      - id: sda2
        type: partition
        size: 2G
        flag: logical
        device: sda
      - id: sda3
        type: partition
        size: 3G
        flag: logical
        device: sda
      - id: volgroup1
        name: vg1
        type: lvm_volgroup
        devices:
            - sda2
            - sda3
      - id: lvmpart1
        name: lv1
        size: 1G
        type: lvm_partition
        volgroup: volgroup1
      - id: lvmpart2
        name: lv2
        type: lvm_partition
        volgroup: volgroup1
      - id: sda1_root
        type: format
        fstype: ext4
        volume: sda1
      - id: lv1_fs
        name: storage
        type: format
        fstype: fat32
        volume: lvmpart1
      - id: lv2_fs
        name: storage
        type: format
        fstype: ext3
        volume: lvmpart2
      - id: sda1_mount
        type: mount
        path: /
        device: sda1_root
      - id: lv1_mount
        type: mount
        path: /srv/data
        device: lv1_fs
      - id: lv2_mount
        type: mount
        path: /srv/backup
        device: lv2_fs

Bcache
~~~~~~

::

  storage:
    version: 1
    config:
      - id: id_rotary0
        type: disk
        name: rotary0
        path: /dev/vdb
        ptable: msdos
        wipe: superblock
        grub_device: true
      - id: id_ssd0
        type: disk
        name: ssd0
        path: /dev/vdc
        wipe: superblock
      - id: id_rotary0_part1
        type: partition
        name: rotary0-part1
        device: id_rotary0
        number: 1
        size: 999M
        wipe: superblock
      - id: id_rotary0_part2
        type: partition
        name: rotary0-part2
        device: id_rotary0
        number: 2
        size: 9G
        wipe: superblock
      - id: id_bcache0
        type: bcache
        name: bcache0
        backing_device: id_rotary0_part2
        cache_device: id_ssd0
        cache_mode: writeback
      - id: bootfs
        type: format
        label: boot-fs
        volume: id_rotary0_part1
        fstype: ext4
      - id: rootfs
        type: format
        label: root-fs
        volume: id_bcache0
        fstype: ext4
      - id: rootfs_mount
        type: mount
        path: /
        device: rootfs
      - id: bootfs_mount
        type: mount
        path: /boot
        device: bootfs

RAID Boot
~~~~~~~~~

::

  storage:
    version: 1
    config:
       - id: sda
         type: disk
         ptable: gpt
         model: QEMU HARDDISK
         path: /dev/vdb
         name: main_disk
         grub_device: 1
       - id: bios_boot_partition
         type: partition
         size: 1MB
         device: sda
         flag: bios_grub
       - id: sda1
         type: partition
         size: 3GB
         device: sda
       - id: sdb
         type: disk
         ptable: gpt
         model: QEMU HARDDISK
         path: /dev/vdc
         name: second_disk
       - id: sdb1
         type: partition
         size: 3GB
         device: sdb
       - id: sdc
         type: disk
         ptable: gpt
         model: QEMU HARDDISK
         path: /dev/vdd
         name: third_disk
       - id: sdc1
         type: partition
         size: 3GB
         device: sdc
       - id: mddevice
         name: md0
         type: raid
         raidlevel: 5
         devices:
           - sda1
           - sdb1
           - sdc1
       - id: md_root
         type: format
         fstype: ext4
         volume: mddevice
       - id: md_mount
         type: mount
         path: /
         device: md_root


RAID5 + Bcache
~~~~~~~~~~~~~~

::

  storage:
    config:
    - grub_device: true
      id: sda
      model: QEMU HARDDISK
      name: sda
      ptable: msdos
      path: /dev/vdb
      type: disk
      wipe: superblock
    - id: sdb
      model: QEMU HARDDISK
      name: sdb
      path: /dev/vdc
      type: disk
      wipe: superblock
    - id: sdc
      model: QEMU HARDDISK
      name: sdc
      path: /dev/vdd
      type: disk
      wipe: superblock
    - id: sdd
      model: QEMU HARDDISK
      name: sdd
      path: /dev/vde
      type: disk
      wipe: superblock
    - id: sde
      model: QEMU HARDDISK
      name: sde
      path: /dev/vdf
      type: disk
      wipe: superblock
    - devices:
      - sdc
      - sdd
      - sde
      id: md0
      name: md0
      raidlevel: 5
      spare_devices: []
      type: raid
    - device: sda
      id: sda-part1
      name: sda-part1
      number: 1
      size: 1000001536B
      type: partition
      uuid: 3a38820c-d675-4069-b060-509a3d9d13cc
      wipe: superblock
    - device: sda
      id: sda-part2
      name: sda-part2
      number: 2
      size: 7586787328B
      type: partition
      uuid: 17747faa-4b9e-4411-97e5-12fd3d199fb8
      wipe: superblock
    - backing_device: sda-part2
      cache_device: sdb
      cache_mode: writeback
      id: bcache0
      name: bcache0
      type: bcache
    - fstype: ext4
      id: sda-part1_format
      label: ''
      type: format
      uuid: 71b1ef6f-5cab-4a77-b4c8-5a209ec11d7c
      volume: sda-part1
    - fstype: ext4
      id: md0_format
      label: ''
      type: format
      uuid: b031f0a0-adb3-43be-bb43-ce0fc8a224a4
      volume: md0
    - fstype: ext4
      id: bcache0_format
      label: ''
      type: format
      uuid: ce45bbaf-5a44-4487-b89e-035c2dd40657
      volume: bcache0
    - device: bcache0_format
      id: bcache0_mount
      path: /
      type: mount
    - device: sda-part1_format
      id: sda-part1_mount
      path: /boot
      type: mount
    - device: md0_format
      id: md0_mount
      path: /srv/data
      type: mount
    version: 1
