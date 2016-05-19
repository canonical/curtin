=======
Storage
=======

Curtin supports a user-configurable storage layout.  This format lets users
(including via MAAS) to customize their machines' storage configuration by
creating partitions, raids, lvms, formating with file systems and setting
mount points.

Basic Configuration Layout
~~~~~~~~~~~~~~~~~~~~~~~~~~
Custom storage configuration is handled by the ``block-meta custom`` command
in curtin. Partitioning layout is read as a list of modifications to make to
achieve the desired configuration. The top level configuration key containing
this configuration is ``storage``. This key should contain a dictionary, with
at least a version number and the configuration list. The current config
specification is ``version: 1``.

**Config Example**::

 storage:
   version: 1
   config:
     - id: sda
       type: disk
       ptable: gpt
       serial: QM00002
       model: QEMU_HARDDISK

Configuration List Entries
~~~~~~~~~~~~~~~~~~~~~~~~~~
Each entry in the config list is a dictionary with several keys which vary
between commands. The two dictionary keys that every entry in the list needs
to have are ``id: <id>`` and ``type: <type>``.

An entry's ``id`` is a reference for the entry that is used internally in the
config file. It can be any string other than one with a special meaning in
yaml, such as ``true`` or ``none``, and it will never be used for anything
other than internal reference.

An entry's ``type`` tells curtin what type of command this config entry should
be running. Available commands include:

- disk
- partition
- format
- mount
- lvm_volgroup
- lvm_partition
- dm_crypt
- raid
- bcache

Disk Command
~~~~~~~~~~~~
The disk command sets up disks for use by curtin. It can wipe the disks, create
partition tables, or just verify that the disks exist and already have a
partition table. A disk command can contain all or some of the following keys:

**ptable**: *msdos, gpt*

If the ``ptable`` key is present and a valid type of partition table, curtin
will create an empty partition table on the disk. At the moment, msdos and
gpt partition tables are supported.

**serial**: *<serial number>*

In order to uniquely identify a disk on the system its serial number should be
specified. This ensures that even if additional storage devices
are added to the system during installation, or udev rules cause the path to a
disk to change curtin will still be able to correctly identify the disk it
should be operating on using ``/dev/disk/by-uuid``.

This is the preferred way to identify a disk, and should be used in all
production environments because it is more reliable than specifying a path.

**path**: *<path>*

If the ``serial`` key is not specified, and the ``path`` key is, then curtin
will use this path for the disk. If both ``serial`` and ``path`` are specified,
curtin will use the serial number and ignore the path that was specified, as
the serial number more uniquely identifies the disk.

In a testing environment or in a VM it can be safe to use ``path`` instead of
``serial`` to identify a disk, because the environment will be consistent
across reboots. However, it is preferable to use ``serial``.

**model**: *<disk model>*

This can specify the manufacturer or model of the disk. It is not currently
used by curtin, but can be useful for a human reading a config file. Future
versions of curtin may make use of this information.

**wipe**: *superblock, pvremove, zero, random*

If wipe is specified, the disk will be wiped. If any of the commands fail to
run due to not finding the information that they were supposed to wipe
installation will not stop. This means it is possible to tell curtin to wipe a
disk without having to know what is on the disk if you do not care about
preserving data.

If curtin has been told to wipe a disk, then before any wipe commands are run,
curtin attempts to shut down any filesystem layers that depend on the disk.
This is done by reading through sysfs and working up to the top filesystem
layer then shutting everything down in order cleanly. For example, if a disk
is being used in a raid array, and bcache is running on top of that raid array,
curtin will shut down bcache, then the raid array, then wipe the disk. By doing
this, curtin can ensure that it can cleanly install onto disks that have
already been used in another system without rebooting.

Most of the time, ``wipe: superblock`` will be enough. This uses
``sgdisk --zap-all`` to erase disk data. If a msdos partition table
is present, ``sgdisk`` will correctly wipe it as
well as the mbr, and if a gpt partition table is present, ``sgdisk`` will wipe
both the primary and secondary gpt header.

If the whole disk has been previously used as a lvm pv, then ``wipe pvremove``
will use ``pvremove`` to erase the lvm header on the disk.

If ``wipe: zero`` is used, the entire disk will be zeroed out using ``dd
if=/dev/zero``. This will take a long time to complete, but makes it much
harder to recover data that was previously on the disk, which may be useful.

If ``wipe: random`` is used, the entire disk will be overwritten with
pseudo-random numbers using ``dd if=/dev/urandom``. This should be used in
situations where sensitive data could have previously been on the disk, or
before using the disk with dm-crypt.

**preserve**: *true, false*

If the preserve key is present and set to ``true``, then curtin will attempt
to use the disk without damaging data present on it. If ``preserve`` is set and
``ptable`` is also set, then curtin will validate that the partition table
specified by ``ptable`` exists on the disk and will raise an error if it does
not. If ``preserve`` is set and ``ptable`` is not, then curtin will be able to
use the disk in later commands, but will not check if the disk has a valid
partition table, and will only verify that the disk exists.

Because it can be dangerous to try to move or resize filesystems and partitions
containing data that needs to be preserved, curtin does not support preserving
a disk without also preserving the partitions on it. If a disk is set to be
preserved and curtin is told to move a partition on that disk, installation
will stop. It is still possible to reformat partitions that do not need to be
preserved.

**name**: *<name>*

If the ``name`` key is present, curtin will create a udev rule that makes a
link to the disk with the given device name. This makes it easy to find disks
on an installed system. The links are created in ``/dev/disk/by-dname/<name>``.
A link to each partition on the disk will also be created at
``/dev/disk/by-dname/<name>-part<number>``, so if ``name: maindisk`` is set,
the disk will be at ``/dev/disk/by-dname/maindisk`` and the first partition on
it will be at ``/dev/disk/by-dname/maindisk-part1``.

**grub_device**: *true, false*

If the ``grub_device`` key is present and set to true, then when post
installation hooks are run grub will be installed onto this disk. In most
situations it is not necessary to specify which disk to install grub onto, as
the post installation hooks will try to figure out the appropriate disk to
install grub onto. However, when the boot device is on a special volume, such
as a raid array or a lvm logical volume, it may be necessary to tell curtin
which disk to install grub on.

**Config Example**::

 - id: sda
   type: disk
   ptable: gpt
   serial: QM00002
   model: QEMU_HARDDISK
   name: maindisk
   wipe: superblock

Partition Command
~~~~~~~~~~~~~~~~~
The partition command creates a single partition on a disk. Curtin only needs
to be told what disk to create the partition on and what size the partition
should be, but additional options can be specified as well.

**number**: *<number>*

The partition number can be specified using ``number``. However, numbers must
be in order and some situations, such as extended/logical partitions on msdos
partition tables will require special numbering, so it is often best to leave
determining partition numbers to curtin. If the ``number`` key is not present,
curtin will determine the right number to use.

**size**: *<size>*

The partition size can be specified with the ``size`` key. Sizes should be
given with an appropriate SI unit, such as *B, kB, MB, GB, TB*, or using just
the appropriate SI prefix, i.e. *B, k, M, G, T...*

**device**: *<device id>*

The ``device`` key refers to the ``id`` of a disk in the storage configuration.
The disk must be placed higher up in the list of commands to ensure that it has
already been processed.

**wipe**: *superblock, pvremove, zero, random*

After the partition is added to the disk's partition table, curtin can run one
of its wipe commands on the partition. The wipe commands are the same as those
for disks.

This can be useful for writing random data over only a part of a disk to save
time but still ensure security if that partition is to be encrypted. This can
also be useful if a partition is created with its start one sector before a lvm
or raid superblock left over from a previous installation, as this could cause
unexpected behavior if not erased.

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

If the host system for curtin has been booted using uefi then curtin will
install grub to the esp partition. If the system installation media
has been booted using an mbr, grub will be installed onto the disk's mbr.
However, on a disk with a gpt partition table, there is not enough space after
the mbr for grub to store its second stage core.img, so a small unformatted
partition with the *bios_grub* flag is needed. This partition should be placed
at the beginning of the disk and should be 1MB in size. It should not contain a
filesystem or be mounted anywhere on the system.

**preserve**: *true, false*

If the preserve flag is set to true, curtin will verify that the partition
exists and will not modify the partition.

**Config Example**::

 - id: sda1
   type: partition
   number: 1
   size: 8GB
   device: sda
   flag: boot

Format Command
~~~~~~~~~~~~~~
The format command makes filesystems on a disk. The filesystem type and target
volume can be specified, as well as a few other options.

**fstype**: ext4, ext3, fat32, fat16, swap

The ``fstype`` key specifies what type of format curtin should use for this
volume. Curtin knows about common linux filesystems such as ext4/3 and fat
filesystems. If it is told to use a filesystem it does not know about, curtin
will check if ``mkfs.<fstype>`` exists and if it does, curtin will try to run
it on the target volume.

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

**name**: *<volume name>*

The ``name`` key tells curtin to create a filesystem name when formatting a
volume. Note that not all filesystem types support names and that there are
length limits for names. For fat filesystems, names are limited to 11
characters. For ext4/3 filesystems, names are limited to 16 characters.

If curtin does not know about the filesystem type it is using, then the
``name`` key will be ignored, because curtin will not know the correct flags to
use to set name.

**uuid**: *<uuid>*

If the ``uuid`` key is set and ``fstype`` is set to *ext4* or *ext3*, then
curtin will set the uuid of the new filesystem to the specified value.

**preserve**: *true, false*

If the ``preserve`` key is set to true, curtin will not format the partition.

**Config Example**::

 - id: sda1_fs
   type: format
   fstype: ext4
   volume: sda1

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

In addition, during system installation, before files
are copied, curtin will mount the target device in the correct place within its
working directory so that any files that should be copied over into its
mountpoint will be present there when the installed system boots.

If the device specified is formatted as swap space, then an entry will be added
to the target system's ``/etc/fstab`` to make use of this swap space.

When entries are created in ``/etc/fstab``, curtin will use the most reliable
method available to identify each device. For regular partitions, curtin will
use the uuid of the filesystem present on the partition. For special devices,
such as raid arrays, or lvm logical volumes, curtin will use their normal path
in ``/dev``.

**device**: *<device id>*

The ``device`` key refers to the ``id`` of the target device in the storage
config. The target device must already contain a valid filesystem and be
accessible.

**Config Example**::

 - id: sda1_mount
   type: mount
   path: /home
   device: sda1_fs

Lvm Volgroup Command
~~~~~~~~~~~~~~~~~~~~
The lvm_volgroup command creates physical volumes and connects them in a
volgroup. It requires a name for the volgroup and a list of the devices that
should be used as physical volumes.

**name**: *<name>*

The ``name`` key tells curtin what the name of the volgroup should be. Almost
anything can be used except words with special meanings in yaml, such as *true*,
or *none*.

**devices**: *[]*

The ``devices`` key gives a list of devices to use as physical volumes. Each
device is specified using the ``id`` of the device higher up in the storage
config. Almost anything can be used as a device, partitions, whole disks, md
arrays and more should work.

**Config Example**::

 - id: volgroup1
   type: lvm_volgroup
   name: vg1
   devices:
     - sda2
     - sdb

Lvm Partition Command
~~~~~~~~~~~~~~~~~~~~~
The lvm_partition command creates a lvm logical volume on the specified
volgroup with the specified size. It also assigns it the specified name.

**name**: *<name>*

The ``name`` key tells curtin what the name of the lvm logical volume should
be. This name is important because this name will be part of the path to the
logical volume, and the logical volume cannot be created without a name.

Like with disks, udev rules will be created for logical volumes to give them
consistently named links inside ``/dev/disk/by-dname/``. These links will
follow the pattern ``<volgroup name>-<logical volume name>``, so a logical
volume named *lv1* on a volgroup named *vg1* would have the path
``/dev/disk/by-dname/vg1-lv1``.

**volgroup**: *<volgroup id>*

The ``volgroup`` key tells curtin which lvm volgroup to create the logical
volume on. The volgroup must already have been created and must have enough
free space on it to create the logical volume. The volgroup should be specified
using the ``id`` key of the volgroup in the storage config, not the name of the
volgroup.

**size**: *<size>*

The ``size`` key tells curtin what size to make the logical volume. The size
can be entered in any format that can be processed by the lvm2 tools, so a
number followed by a SI unit should work, i.e. *B, kB, MB, GB, TB*.

If the ``size`` key is omitted then all remaining space on the volgroup will be
used for the logical volume.

**Config Example**::

 - id: lvm_partition_1
   type: lvm_partition
   name: lv1
   volgroup: volgroup1
   size: 10G

Dm-Crypt Command
~~~~~~~~~~~~~~~~
The dm_crypt command creates encrypted volumes using ``cryptsetup``. It
requires a name for the encrypted volume, the volume to be encrypted and a key.
Note that this should not be used for systems where security is extremely
important, because the key is stored in plaintext in the storage configuration
and it could be possible for the storage configuration to be intercepted
between the utility that generates it and curtin.

**volume**: *<volume id>*

The ``volume`` key gives the volume that is to be encrypted. In most situations
this will be a partition. It is usually a good idea to use ``wipe: random`` on
the volume that is going to be encrypted.

**dm_name**: *<name>*

The ``name`` key specifies the name that the encrypted volume should have.

**key**: *<key>*

The ``key`` key specifies the password that the encryption key should be
secured with. This is the password that must be entered in order to mount the
disk.

Note that when the dm_crypt command encrypts a disk, it is added to
``/etc/crypttab`` and it should be mounted at boot because of this. Also, when
post installation hooks are run, the initial ramdisk of the installed system
will be regenerated so that the cryptodisks hooks will be applied to it and the
installed system will be able to mount encrypted volumes at boot.

**Config Example**::

 - id: lvm_partition_1
   type: dm_crypt
   dm_name: crypto
   volume: sdb1
   key: testkey

Raid Command
~~~~~~~~~~~~
The raid command can set up software raid using mdadm. It needs to be given a
name for the md device it is creating, a list of volumes to use as the raid
devices, optionally, a second list to be used as spare devices, and the
raid level it should use.

**name**: *<name>*

The ``name`` key specifies the name that should be used for the md device.

Note that a udev rule will be written to create a link to the md device in
``/dev/disk/by-dname/<name>`` using the specified name.

**raidlevel**: *0, 1, 5*

The ``raidlevel`` key specifies the raid level that should be used by mdadm.

**devices**: *[]*

The ``devices`` key specifies a list of the devices that should be used for the
raid array. Each device should refer by ``id`` to a device that exists earlier
in the storage configuration. Devices can either be partitions or full disks.
Note that it is not always possible to boot a system off of a disk that has
been used entirely as a raid device, as the raid metadata takes up some of the
space that grub needs for its second stage core.img.

**spare_devices**: *[]*

The ``spare_devices`` key specifies a list of devices to be used as spares in
case one of the main devices in the raid array fails. It, like ``devices``
should be a list of storage config partitions or disks referenced by their
``id``.

**ptable**: *msdos, gpt*

If the ``ptable`` key is present, curtin will create a partition table on the
md array. It is then possible to use the partition command to create partitions
on this partition table, and the partitions can be used normally. Either
*msdos* or *gpt* partition tables can be used.

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
The bcache command can use a fast storage device such as a ssd as a
writethrough cache for another, slower volume such as a raid array
using the bcache kernel module. The bcache command needs to be told which
device to use as its backing device and which device to use as its cache
device.

**backing_device**: *<device id>*

The ``backing_device`` key specifies the item in storage configuration to use
as the backing device. This can be any device that would normally be used with
a filesystem on it, such as a partition or a raid array.

**cache_device**: *<device id>*

The ``cache_device`` key specifies the item in the storage configuration to use
as the cache device. This can be a partition or a whole disk. It should be on a
ssd in most cases, as bcache is designed around the performance characteristics
of a ssd.

**name**: *<name>*

If the ``name`` key is present, curtin will create a link to the device at
``/dev/disk/by-dname/<name>``.

**Config Example**::

 - id: bcache0
   type: bcache
   name: cached_raid
   backing_device: raid_array
   cache_device: sdb
