.. _storage:

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
dictionary with at least a version number and the configuration list.

**Config Example**::

 storage:
   version: 1
   config:
     - id: sda
       type: disk
       ptable: gpt
       serial: QM00002
       model: QEMU_HARDDISK

The ``storage`` configuration can also have a ``device_map_path`` key
that specifies a file path where curtin will record (in JSON format) a
mapping from device id as specified in the action to the path to the
device node for the block device this action ended up modifying or
creating.

Config versions
---------------

The current version of curtin supports versions ``1`` and ``2``. These
only differ in the interpretation of ``partition`` actions at this
time. ``lvm_partition`` actions will be interpreted differently at
some point in the future.

.. note::

  Config version ``2`` is under active development and subject to change.
  Users are advised to use version ``1`` unless features enabled by version
  ``2`` are required.

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

- Dasd Command (``dasd``)
- Disk Command (``disk``)
- Partition Command (``partition``)
- Format Command (``format``)
- Mount Command  (``mount``)
- LVM_VolGroup Command (``lvm_volgroup``)
- LVM_Partition Command (``lvm_partition``)
- DM_Crypt Command (``dm_crypt``)
- RAID Command (``raid``)
- Bcache Command (``bcache``)
- Zpool Command (``zpool``) **Experimental**
- ZFS Command (``zfs``)) **Experimental**
- NVMe Controller Command (``nvme_controller``) **Experimental**
- Device "Command" (``device``)

Any action that refers to a block device (so things like ``partition``
and ``dm_crypt`` but not ``lvm_volgroup`` or ``mount``, for example)
*can* specify a ``path`` key but aside from ``disk`` actions this is
not used to locate the device. A warning will be emitted if the
located device does not match the provided path though.

Dasd Command
~~~~~~~~~~~~

The ``dasd`` command sets up an ECKD s390x system DASD device for use
by curtin.  FBA DASD devices do not require this low level set
up. ECKD DASD drives can also be passed via virtio to KVM virtual
machines and in this case this set up must be done on the host prior
to starting the virtual machine.

DASD devices require several parameters to configure the low-level
structure of the block device.  Curtin will examine the configuration
and determine if the specified DASD matches the configuration.  If the
device does not match the configuration Curtin will perform a format
of the device to achieve the required configuration.  Once a DASD
device has been formatted it may be used like regular Linux block
devices and can be partitioned (with limitations) with Curtin's
``disk`` command.  The ``dasd`` command may contain the following
keys:

**device_id**: *<ccw bus_id: X.Y.ZZZZ>*

The ``device_id`` value is used to select a specific DASD device.

**blocksize**: *512, 1024, 2048, 4096*

Specify blocksize to be used. ``blocksize`` must be a positive integer and
always be a power of two. The default blocksize is 4096 bytes.

.. note::

  The net capacity of an ECKD™ DASD decreases for smaller block sizes. For
  example, a DASD formatted with a block size of 512 byte has only half of the
  net capacity of the same DASD formatted with a block size of 4096 byte.

**mode**: *quick, full,  expand*

Specify the mode to be used to format the device.  The default mode is ``full``
which will format the entire disk.

Using ``quick`` mode will format the first two tracks and write label and
partition information.  Only use this option if you are sure that the target
DASD has already been formatted in a ``disk_layout`` and ``blocksize`` desired.

The ``expand`` mode will format all unformatted tracks at the end of the target
DASD.  This mode assumes that tracks at the beginning of the DASD volume have
already been correctly formatted.

**label**: *<label>*

The ``label`` value sets the volume serial number (volser) that will be written
to the specified DASD after formatting.  If no ``label`` value is provided one
will be generated.  The value provided is interpreted as ASCII string and
converted to uppercase and then to EBCDIC.

Valid labels are 6 characters long and can alphanumeric values, $, #, @, and %.
Shorter values will be padded with trailing spaces.

These ``label`` values are reserved and cannot be used:

  MIGRAT, SCRTCH, PRIVAT, or Lnnnnn (L with five numbers);

**disk_layout**: *cdl, ldl*

The default ``disk_layout`` value is ``cdl``, the compaible disk layout which
allows for up to 3 partitions and a VTOC.  The ``ldl``, Linux layout has only
one partition.


**Config Example**::

 - id: dasd_root
   type: dasd
   device_id: 0.0.1520
   blocksize: 4096
   disk_layout: cdl
   label: 0X1520
   mode: full
 - id: disk0
   type: disk
   ptable: vtoc
   serial: 0X1520
   name: root_disk
   wipe: superblock



Disk Command
~~~~~~~~~~~~
The disk command sets up disks for use by curtin. It can wipe the disks, create
partition tables, or just verify that the disks exist with an existing partition
table. A disk command may contain all or some of the following keys:

**ptable**: *msdos, gpt, vtoc*

If the ``ptable`` key is present and a curtin will create an empty
partition table of that type on the disk.  On almost all drives,
curtin supports msdos and gpt partition tables; ECKD DASD drives on
s390x mainframes can only use the "vtoc" partition table.

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

**wipe**: *superblock, superblock-recursive, pvremove, zero, random*

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

The ``wipe: pvremove`` option will execute the ``pvremove`` command to
wipe the LVM metadata so that the device is no longer part of an LVM.


**preserve**: *true, false*

When the preserve key is present and set to ``true`` curtin will attempt
reuse the existing storage device.  Curtin will verify aspects of the device
against the configuration provided.  For example, when assessing whether
curtin can use a preserved partition, curtin checks that the device exists,
size of the partition matches the value in the config and checks if the same
partition flag is set.  The set of verification checks vary by device type.
If curtin encounters a mismatch between config and what is found on the
device a RuntimeError will be raised with the expected and found values and
halt the installation.  Currently curtin will verify the follow storage types:

- disk
- partition
- lvm_volgroup
- lvm_partition
- dm_crypt
- raid
- bcache
- format

One specific use-case of ``preserve: true`` is in conjunction with the ``wipe``
flag.  This allows a device to reused, but have the *content* of the device to
be removed.

**name**: *<name>*

If the ``name`` key is present, curtin will create a udev rule that makes a
symbolic link to the disk with the given name value. This makes it easy to find
disks on an installed system. The links are created in
``/dev/disk/by-dname/<name>``.  The udev rules will utilize two types of disk
metadata to construct the link.  For disks with ``serial`` and/or ``wwn`` values
these will be used to ensure the name persists even if the contents of the disk
change.  For legacy purposes, curtin also emits a rule utilizing metadata on
the disk contents, typically a partition UUID value, this also preserves these
links for disks which lack persistent attributes such as a ``serial`` or
``wwn``, typically found on virtualized environments where such values are left
unset.

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

**multipath**: *<multipath name or serial>*

If a disk is a path in a multipath device, it may be included in the
configuration dictionary.  Currently the value is informational only.
Curtin already detects whether disks are part of a multipath and selects
one member path to operate upon.

**nvme_controller**: *<NVMe controller id>*

If the disk is a NVMe SSD, the ``nvme_controller`` key can be set to the
identifier of a ``nvme_controller`` object. This will help to determine the
type of transport used (e.g., PCIe vs TCP).

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

Partition actions are interpreted differently according to the version of the
storage config.

 * For version 1 configs, the actions are handled one by one and each
   partition is created (or assumed to exist, in the ``preserve: true`` case)
   just after that described by the previous action.

 * For version 2 configs, the actions are bundled together to create a
   complete description of the partition table, and the ``offset`` of each
   action is respected if present. Any partitions that already exist but are
   not referenced in the new config are (superblock-) wiped and deleted.

   * Because the numbering of logical partitions is not stable (i.e. if there
     are two logical partitions numbered 5 and 6, and partition 5 is deleted,
     what was partition 6 will become partition 5), curtin checks if a
     partition is deleted or not by checking for the presence of a partition
     action with a matching offset.

If the disk is being completely repartitioned, the two schemes are effectively
the same.

**number**: *<number>*

The partition number can be specified using ``number``.

For GPT partition tables, this will just be the slot in the partition table
that is used to describe this partition.

For DOS partition tables, a primary or extended partition must have a number
less than or equal to 4. Logical partitions have numbers 5 or greater but are
numbered by the order they are found when parsing the partitions, so the
``number`` field is ignored for them.

If the ``number`` key is not present, curtin will attempt determine the right
number to use.

**size**: *<size>*

The partition size can be specified with the ``size`` key. Sizes must be
given with an appropriate SI unit, such as *B, kB, MB, GB, TB*, or using just
the appropriate SI prefix, i.e. *B, k, M, G, T...*

Curtin interprets size units in power-of-2 style.  This means that
``1kB`` is the same as ``1k`` and ``1024``, and so on for all the prefixes.

.. note::

  Curtin does not adjust or inspect size values.  If you specify a size that
  exceeds the capacity of a device then installation will fail.

**offset**: *<offset>*

The offset at which to create the partition. Only respected in a version 2
config. If the offset field is not present, the partition will be placed after
that described by the preceding (logical or primary, if appropriate) partition
action, or at the start of the disk (or extended partition, as appropriate).

**device**: *<device id>*

The ``device`` key refers to the ``id`` of a disk in the storage configuration.
The disk entry must already be defined in the list of commands to ensure that
it has already been processed.

**wipe**: *superblock, superblock-recursive, pvremove, zero, random*

After the partition is added to the disk's partition table, curtin can run a
wipe command on the partition. The wipe command values are the sames as for
disks.

.. note::

  Curtin will automatically wipe 1MB at the starting location of the partition
  prior to creating the partition to ensure that other block layers or devices
  do not enable themselves and prevent accessing the partition.

**flag**: *logical, extended, boot, bios_grub, swap, lvm, raid, home, prep, msftres*

If the ``flag`` key is present, curtin will set the specified flag on the
partition. Note that some flags only apply to msdos partition tables, and some
only apply to gpt partition tables.

The *logical/extended* partition flags can be used to create logical partitions
on a msdos table. An extended partition should be created containing all of the
empty space on the drive, and logical partitions can be created within it. A
extended partition must already be present to create logical partitions.

On msdos partition tables, the *boot* flag sets the boot parameter to
that partition. On gpt partition tables, the boot flag sets partition
type guid to the appropriate value for the EFI System Partition / ESP.

If the host system for curtin has been booted using UEFI then curtin will
install grub to the esp partition. If the system installation media
has been booted using an MBR, grub will be installed onto the disk's MBR.
However, on a disk with a gpt partition table, there is not enough space after
the MBR for grub to store its second stage core.img, so a small un-formatted
partition with the *bios_grub* flag is needed. This partition should be placed
at the beginning of the disk and should be 1MB in size. It should not contain a
filesystem or be mounted anywhere on the system.

**partition_type**: *msdos: byte value in 0xnn style; gpt: GUID*

Only applicable to v2 storage configuration.  If both ``partition_type`` and
``flag`` are set, ``partition_type`` dictates the actual type.

The ``partition_type`` field allows for setting arbitrary partition type values
that do not have a matching ``flag``, or cases that are not handled by the
``flag`` system.  For example, since the *boot* flag results in both setting
the bootable state for a MSDOS partition table and setting it to type *0xEF*,
one can override this behavior and achieve a bootable partition of a different
type by using ``flag``: *boot* and using ``partition_type``.

**preserve**: *true, false*

If the preserve flag is set to true, curtin will verify that the partition
exists and that  the ``size`` and ``flag`` match the configuration provided.
See also the ``resize`` flag, which adjusts this behavior.

**resize**: *true, false*

Only applicable to v2 storage configuration.
If the ``preserve`` flag is set to false, this value is not applicable.
If the ``preserve`` flag is set to true, curtin will adjust the size of the
partition to the new size.  When adjusting smaller, the size of the contents
must permit that.  When adjusting larger, there must already be a gap beyond
the partition in question.
Resize is supported on filesystems of types ext2, ext3, ext4, ntfs.

**name**: *<name>*

If the ``name`` key is present, curtin will create a udev rule that makes a
symbolic link to the partition with the given name value. The links are created
in ``/dev/disk/by-dname/<name>``.

For partitions, the udev rule created relies upon disk contents, in this case
the partition entry UUID.  This will remain in effect unless the underlying disk
on which the partition resides has the partition table modified or wiped.
This value differs from the ``partition_name`` field below.

**partition_name** *<name for gpt table partition entry>*

Only applicable with a gpt ``ptable``.
This value is not the same as the ``name`` field above.
This field sets the optional freeform ASCII name string on the partition.
On preserved partitions, if this value is unspecified, the current name will be
retained.

**uuid**: *<uuid>*

Only applicable with a gpt ``ptable``.
This field sets the optional UUID value on the partition.
On preserved partitions, if this value is unspecified, the current UUID will be
retained.

**attrs**: *<list of strings in sfdisk(8) format>*

Only applicable with a gpt ``ptable``.
Partition attribute flags may optionally be set.  These flags must be specified
in the same format that
`sfdisk(8) <https://manpages.ubuntu.com/manpages/focal/man8/sfdisk.8.html#commands>`_
expects for the part-attrs argument.
On preserved partitions, if this value is unspecified, the current attributes
will be retained.

**multipath**: *<multipath name or serial>*

If a partition is found on a multipath device, it may be included in the
configuration dictionary.  Currently the value is informational only.
Curtin already detects whether partitions are part of a multipath and selects
one member path to operate upon.


**Config Example**::

 - id: disk0-part1
   type: partition
   number: 1
   size: 8GB
   device: disk0
   flag: boot
   name: boot_partition

.. _format:

Format Command
~~~~~~~~~~~~~~
The format command makes filesystems on a volume. The filesystem type and
target volume can be specified, as well as a few other options.

**fstype**: ext4, ext3, f2fs, fat32, fat16, swap, xfs, zfsroot

.. note::

  Filesystems support for ZFS on root is **Experimental**.
  Utilizing the the ``fstype: zfsroot`` will indicate to curtin
  that it should automatically inject the appropriate ``type: zpool``
  and ``type: zfs`` command structures based on which target ``volume``
  is specified in the ``format`` command.  There may be only *one*
  zfsroot entry.  The disk that contains the zfsroot must be partitioned
  with a GPT partition table.  Curtin will fail to install if these
  requirements are not met.

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

**extra_options**: *<list of strings>*

The ``extra_options`` key is a list of strings that is appended to the mkfs
command used to create the filesystem.  **Use of this setting is dangerous.
Some flags may cause an error during creation of a filesystem.**

**Config Example**::

 - id: disk0-part1-fs1
   type: format
   fstype: ext4
   label: cloud-image
   volume: disk0-part1

 - id: disk1-part1-fs1
   type: format
   fstype: ext4
   label: osdata1
   uuid: ed51882e-8688-4cd8-97ca-1f2b8bbee458
   extra_options: ['-O', '^metadata_csum,^64bit']

 - id: nvme1-part1-fs1
   type: format
   fstype: ext4
   label: cacheset1
   extra_options:
     - -E
     - offset=1024,nodiscard

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

The ``device`` key refers to the ``id`` of a :ref:`Format <format>` entry.
One of ``device`` or ``spec`` must be present.

.. note::

  If the specified device refers to an iSCSI device, the corresponding
  fstab entry will contain ``_netdev`` to indicate networking is
  required to mount this filesystem.

**freq**: *<dump(8) integer from 0-9 inclusive>*

The ``freq`` key refers to the freq as defined in dump(8).
Defaults to ``0`` if unspecified.

**fstype**: *<fileystem type>*

``fstype`` is only required if ``device`` is not present.  It indicates
the filesystem type and will be used for mount operations and written
to ``/etc/fstab``

**options**: *<mount(8) comma-separated options string>*

The ``options`` key will replace the default options value of ``defaults``.

.. warning::
  The kernel and user-space utilities may differ between the install
  environment and the runtime environment.  Not all kernels and user-space
  combinations will support all options.  Providing options for a mount point
  will have both of the following effects:

  - ``curtin`` will mount the filesystems with the provided options during the installation.

  - ``curtin`` will ensure the target OS uses the provided mount options by updating the target OS (/etc/fstab).

  If either of the environments (install or target) do not have support for
  the provided options, the behavior is undefined.

**passno**: *<fsck(8) non-negative integer, typically 0-2>*

The ``passno`` key refers to the fs_passno as defined in fsck(8).
If unspecified, ``curtin`` will default to 1 or 0, depending on if that
filesystem is considered to be a 'nodev' device per /proc/filesystems.
Note that per systemd-fstab-generator(8), systemd interprets passno as a
boolean.

**spec**: *<fs_spec>*

The ``spec`` attribute defines the fsspec as defined in fstab(5).
If ``spec`` is present with ``device``, then mounts will be done
according to ``spec`` rather than determined via inspection of ``device``.
If ``spec`` is present without ``device`` then ``fstype`` must be present.


**Config Example**::

 - id: disk0-part1-fs1-mount0
   type: mount
   path: /home
   device: disk0-part1-fs1
   options: 'noatime,errors=remount-ro'

**Bind Mount**

Below is an example of configuring a bind mount.

.. code-block:: yaml

 - id: bind1
   fstype: "none"
   options: "bind"
   path: "/var/lib"
   spec: "/my/bind-over-var-lib"
   type: mount

That would result in a fstab entry like::

  /my/bind-over-var-lib /var/lib none bind 0 0

**Tmpfs Mount**

Below is an example of configuring a tmpfsbind mount.

.. code-block:: yaml

    - id: tmpfs1
      type: mount
      spec: "none"
      path: "/my/tmpfs"
      options: size=4194304
      fstype: "tmpfs"

That would result in a fstab entry like::

  none /my/tmpfs tmpfs size=4194304 0 0


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

**preserve**: *true, false*

If the ``preserve`` option is True, curtin will verify that volume group
specified by the ``name`` option is present and that the physical volumes
of the group match the devices specified in ``devices``.  There is no ``wipe``
option for volume groups.


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

.. note::

   dname values for contructed devices (such as lvm) only remain persistent
   as long as the device metadata does not change.  If users modify the device
   such that device metadata is changed then the udev rule may no longer apply.

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

**preserve**: *true, false*

If the ``preserve`` option is True, curtin will verify that specified lvm
partition is part of the specified volume group.  If ``size`` is specified
curtin will verify the size matches the specified value.

**wipe**: *superblock, superblock-recursive, pvremove, zero, random*

If ``wipe`` option is set, and ``preserve`` is False, curtin will wipe the
contents of the lvm partition.  Curtin skips wipe settings if it creates
the lvm partition.

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

The dm_crypt command creates encrypted volumes using ``cryptsetup``. It requires
a name for the encrypted volume, the volume to be encrypted and a key.  In
situations where the config is generated on a different system from where curtin
is run there is not yet a good solution for securely conveying the key -- you
can set **key** but it appears in plain text in the config, which might be
intercepted by between the systems (and is by default copied to the target
system). If the config is generated on the same system, you can use **keyfile**
to supply the passphrase in file with appropriate permissions.

**volume**: *<volume id>*

The ``volume`` key gives the volume that is to be encrypted.

**dm_name**: *<name>*

The ``name`` key specifies the name of the encrypted volume.

**key**: *<key>*

The ``key`` key specifies the password of the encryption key.  The target
system will prompt for this password in order to mount the disk.

**keyfile**: *<keyfile>*

The ``keyfile`` contains the password of the encryption key.  The target
system will prompt for this password in order to mount the disk.  This keyfile
must exist at the time curtin is run.

A special case of ``keyfile`` are the values ``/dev/urandom`` and
``/dev/random``, which indicate that this ``keyfile`` value will be used in
entirety to decrypt the device.  In this case, the keyfile is passed along to
the crypttab, as the third field.

.. note::
  ``/dev/urandom`` and ``/dev/random`` are functionally equivalent on modern
  systems.

Exactly one of **key** and **keyfile** must be supplied.

**preserve**: *true, false*

If the ``preserve`` option is True, curtin will verify the dm-crypt device
specified is composed of the device specified in ``volume``.

**wipe**: *superblock, superblock-recursive, pvremove, zero, random*

If ``wipe`` option is set, and ``preserve`` is False, curtin will wipe the
contents of the dm-crypt device.  Curtin skips wipe settings if it creates
the dm-crypt volume.

**options**: *<list of man 5 crypttab options strings>*

Options to pass to crypttab, as the fourth field.  See man 5 crypttab for
details. The default is ``[luks]``.

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
  ``/dev/disk/by-dname/<name>`` using the specified name.  The dname
  symbolic link is only persistent as long as the raid metadata is
  not modifed or destroyed.

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

**ptable**: *msdos, gpt*

To partition the array rather than mounting it directly, the
``ptable`` key must be present and a valid type of partition table,
i.e. msdos or gpt.

**metadata**: *default, 1.2, 1.1, 0.90, ddf, imsm*

Specify the metadata (superblock) style to be used when creating the array.
``metadata`` defaults to the string "default" and is passed to mdadm.  The
version of mdadm used during the install will control the value here.  Note
that metadata version 1.2 is the default in mdadm since release version 3.3
in 2013.

**preserve**: *true, false*

If the ``preserve`` option is True, curtin will verify the composition of
the raid device.  This includes array state, raid level, device md-uuid,
composition of the array devices and spares and that all are present.

**wipe**: *superblock, superblock-recursive, pvremove, zero, random*

If ``wipe`` option is set to values other than 'superblock', curtin will
wipe contents of the assembled raid device.  Curtin skips 'superblock` wipes
as it already clears raid data on the members before assembling the array.

To allow a pre-existing (i.e. ``preserve=true``) raid to get a new partition
table, set the ``wipe`` field to indicate the disk should be
reformatted (this is different from disk actions, where the preserve field is
used for this. But that means something different for raid devices).

**Config Example**::

 - id: raid_array
   type: raid
   name: md0
   raidlevel: 1
   metadata: 0.90
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

.. note::

   dname values for contructed devices (such as bcache) only remain persistent
   as long as the device metadata does not change.  If users modify the device
   such that device metadata is changed then the udev rule may no longer apply.

**preserve**: *true, false*

If the ``preserve`` option is True, curtin will verify the composition of
the bcache device.  This includes checking that backing device and cache
device are enabled and bound correctly (backing device is cached by expected
cache device).  If ``cache-mode`` is specified, verify that the mode matches.


**wipe**: *superblock, superblock-recursive, pvremove, zero, random*

If ``wipe`` option is set, curtin will wipe the contents of the bcache device.
If only ``cache`` device is specified, wipe option is ignored.


**Config Example**::

 - id: bcache0
   type: bcache
   name: cached_raid
   backing_device: raid_array
   cache_device: sdb

Zpool Command
~~~~~~~~~~~~~~
ZFS Support is **experimental**.

The zpool command configures ZFS storage pools.  A storage pool is a collection
of devices that provides physical storage and data replication for ZFS datasets.

The zpool command needs to be provided with a list of physical devices, called
vdevs.

.. note::

 Curtin specifies zpool version=28 by default.  This version is the most
 `compatible <http://open-zfs.org/wiki/FAQ#Compatibility>`_
 with other ZFS implementations.  If newer ZFS features are
 required users may specify the version value in the ``pool_properties``
 dictionary.  Users may also run ```zpool upgrade``` to move to a new pool
 version.  Some newer features may require migration of data.

 For more information about versions and features consult:

 http://open-zfs.org/wiki/

**pool**: *<pool name>*

The ``pool`` key specifies the name of the ZFS storage pool.  It will be used
when constructing ZFS datasets.

**vdevs**: *[<device id>]*

The ``vdevs`` key specifies a list of items in the storage configuration to use
in building a ZFS storage pool.  This can be a partition or a whole disk.
It is recommended that vdevs are ``disks`` which have a 'serial' attribute
which allows Curtin to build a /dev/disk/by-id path which is a persistent
path, however, if not available Curtin will accept 'path' attributes but
warn that the zpool may be unstable due to missing by-id device path.

**mountpoint**: *<mountpoint>*

The ``mountpoint`` key specifies where ZFS will mount the storage pool.

**pool_properties**: *{<key=value>}*

The ``pool_properties`` key specifies a dictionary of key=value pairs which
are passed to the ZFS storage pool configuration as properties of the pool.
The default pool properties are:

- ashift: 12
- version: 28

Use ``ashift: null`` or ``version: null``
to use the default value for these properties as decided by ``zpool create``.

**fs_properties**: *{<key=value>}*

The ``fs_properties`` key specifies a dictionary of key=value pairs which
are passed to the ZFS storage pool configuration as the default properties of
any ZFS datasets that are created within the pool.  The default fs properties
are:

- atime: off
- canmount: off
- normalization: formD

Use ``$key: null``, where ``$key`` is one of the default fs_property keys,
to use the default value for these properties as decided by ``zpool create``.

**default_features**: *true, false*

If *true*, keep the default features enabled.  For fine-grained control of the
desired features, set to *false* and enable the desired features with
pool_properties. This controls the presence or absence of the `-d` flag of
`zpool create`. Default value is *true*, which means the zpool default feature
set is used.

**Config Example**::

 - type: zpool
   id: sda_rootpool
   pool: rpool
   vdevs:
    - sda1
   mountpoint: /

**encryption_style**: *luks_keystore, null*

If set to **luks_keystore**, an encrypted pool is created using a LUKS backed
keystore system.  When **encryption_style** is not null, **keyfile** is
required.

This works as follows:

* A LUKS device is created as a ZFS dataset in the ZPool.
* The supplied passphrase (see **keyfile**) is used to encrypt the LUKS device.
* The real key for the ZFS dataset is contained in the LUKS device as a simple
  file.
* The zpool is decrypted using this simple file inside the encrypted LUKS
  device.

Default value is **null**, which means the resulting zpool is unencrypted.

**keyfile**: *<keyfile>*

The ``keyfile`` contains the password of the encryption key.  The target
system will prompt for this password in order to mount the disk.  This keyfile
must exist at the time curtin is run.  In the **luks_keystore** scheme, this
key is used to unlock the keystore, and inside the keystore is a system.key
file which is supplied to ZFS to unlock the pool.

ZFS Command
~~~~~~~~~~~~~~
ZFS Support is **experimental**.

The zfs command configures ZFS datasets within a ZFS storage pool.  A dataset
is identified by a unique path within the ZFS namespace.  A dataset can be one
of the following: filesystem, volume, snapshot, bookmark.

The zfs command needs to be provided with a pool name and a dataset name.

.. note::

 Curtin specifies zpool version=28 by default.  This version is the most
 `compatible <http://open-zfs.org/wiki/FAQ#Compatibility>`_
 with other ZFS implementations.  If newer ZFS features are
 required users may specify the version value in the ``pool_properties``
 dictionary.  Users may also run ```zpool upgrade``` to move to a new pool
 version.  Some newer features may require migration of data.

 For more information about versions and features consult:

 http://open-zfs.org/wiki/


**pool**: *<pool name>*

The ``pool`` key specifies the name of the ZFS storage pool.  It will be used
when constructing ZFS datasets.

**volume**: *<volume name>*

The ``volume`` key specifies the name of the volume to create with the
specified ZFS storage pool.

**properties**: *{key=value}*

The ``properties`` key specifies a dictionary of key=value pairs which are
passed to the ZFS dataset creation command.

**Config Example**::

 - type: zfs
   id: sda_rootpool_rootfs
   pool: sda_rootpool
   volume: /ROOT/zfsroot
   properties:
     canmount: noauto
     mountpoint: /

NVMe Controller Command
~~~~~~~~~~~~~~~~~~~~~~~
NVMe Controller Commands (and NVMe over TCP support in general) are
**experimental**.

The nvme_controller command describes how to communicate with a given NVMe
controller.

**transport**: *pcie, tcp*

The ``transport`` key specifies whether the communication with the NVMe
controller operates over PCIe or over TCP. Other transports like RDMA and FC
(aka. Fiber Channel) are not supported at the moment.

**tcp_addr**: *<ip address>*

The ``tcp_addr`` key specifies the IP where the NVMe controller can be reached.
This key is only meaningful in conjunction with ``transport: tcp``.

**tcp_port**: *port*

The ``tcp_port`` key specifies the TCP port where the NVMe controller can be
reached. This key is only meaningful in conjunction with ``transport: tcp``.

**Config Example**::

 - type: nvme_controller
   id: nvme-controller-nvme0
   transport: pcie

 - type: nvme_controller
   id: nvme-controller-nvme1
   transport: tcp
   tcp_addr: 172.16.82.78
   tcp_port: 4420

Device "Command"
~~~~~~~~~~~~~~~~

This is a special command that can be used to refer to an arbitrary
block device. It can be useful when you want to refer to a device that
has been set up outside curtin for some reason -- partitioning or
formatting or including in a RAID array or LVM volume group, for example.

**path**: *path to device node*

Path or symlink to the device node in /dev.

The device action also supports the **ptable** attribute, to allow an
arbitrary device node to be partitioned.



Additional Examples
-------------------

Learn by examples.

- Basic
- LVM
- Bcache
- RAID Boot
- Partitioned RAID
- RAID5 + Bcache
- ZFS Root Simple
- ZFS Root

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

Partitioned RAID
~~~~~~~~~~~~~~~~

::

  storage:
    config:
    - type: disk
      id: disk-0
      ptable: gpt
      path: /dev/vda
      wipe: superblock
      grub_device: true
    - type: disk
      id: disk-1
      path: /dev/vdb
      wipe: superblock
    - type: disk
      id: disk-2
      path: /dev/vdc
      wipe: superblock
    - type: partition
      id: part-0
      device: disk-0
      size: 1048576
      flag: bios_grub
    - type: partition
      id: part-1
      device: disk-0
      size: 21471690752
    - id: raid-0
      type: raid
      name: md0
      raidlevel: 1
      devices: [disk-2, disk-1]
      ptable: gpt
    - type: partition
      id: part-2
      device: raid-0
      size: 10737418240
    - type: partition
      id: part-3
      device: raid-0
      size: 10735321088,
    - type: format
      id: fs-0
      fstype: ext4
      volume: part-1
    - type: format
      id: fs-1
      fstype: xfs
      volume: part-2
    - type: format
      id: fs-2
      fstype: ext4
      volume: part-3
    - type: mount
      id: mount-0
      device: fs-0
      path: /
    - type: mount
      id: mount-1
      device: fs-1
      path: /srv
    - type: mount
      id: mount-2
      device: fs-2
      path: /home
    version: 1


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

ZFS Root Simple
~~~~~~~~~~~~~~~

::

 storage:
    config:
    - id: sda
      type: disk
      ptable: gpt
      serial: dev_vda
      name: main_disk
      wipe: superblock
      grub_device: true
    - id: sda1
      type: partition
      number: 1
      size: 9G
      device: sda
    - id: bios_boot
      type: partition
      size: 1M
      number: 2
      device: sda
      flag: bios_grub
    - id: sda1_root
      type: format
      fstype: zfsroot
      volume: sda1
      label: 'cloudimg-rootfs'
    - id: sda1_mount
      type: mount
      path: /
      device: sda1_root
    version: 1


ZFS Root
~~~~~~~~

::

 storage:
     config:
     -   grub_device: true
         id: disk1
         name: main_disk
         ptable: gpt
         serial: disk-a
         type: disk
         wipe: superblock
     -   device: disk1
         id: disk1p1
         number: 1
         size: 9G
         type: partition
     -   device: disk1
         flag: bios_grub
         id: bios_boot
         number: 2
         size: 1M
         type: partition
     -   id: disk1_rootpool
         mountpoint: /
         pool: rpool
         type: zpool
         vdevs:
         - disk1p1
     -   id: disk1_rootpool_container
         pool: disk1_rootpool
         properties:
             canmount: 'off'
             mountpoint: 'none'
         type: zfs
         volume: /ROOT
     -   id: disk1_rootpool_rootfs
         pool: disk1_rootpool
         properties:
             canmount: noauto
             mountpoint: /
         type: zfs
         volume: /ROOT/zfsroot
     -   id: disk1_rootpool_home
         pool: disk1_rootpool
         properties:
             setuid: 'off'
         type: zfs
         volume: /home
     -   id: disk1_rootpool_home_root
         pool: disk1_rootpool
         type: zfs
         volume: /home/root
         properties:
             mountpoint: /root
     version: 1
