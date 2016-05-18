=======
Storage
=======

Curtin supports a user-configurable storage layout.  This format lets users
(including via MAAS) to customize their machines' storage configuration by
creating partitions, raids, lvms, formating with file systems and setting
mount points.

Format
------
Curtin accepts a YAML input under the top-level ``storage`` key
to indicate that a user would like to specify a custom storage
configuration.  Required elements of a storage configuration are
``config`` and ``version``.  Currently curtin only supports 
storage config version=1. ::

  storage:
    version: 1
    config:
       
Config Types
------------
Within the storage ``config`` portion, users include a list of configuration
types.  The current list of support ``type`` values are as follows:
  
 - **disk**: 
 - **partition**:
 - **raid**:
 - **lvm**:
 - **bcache**:
 - **format**:
 - **mount**:

Basic example::
  
  storage:
    version: 1
    config:
      - id: disk0
        type: disk
        ptable: msdos
        model: QEMU HARDDISK
        serial: QM00002
        path: /dev/vdb
      - id: sda1
        type: partition
        number: 1
        size: 8GB
        device: disk0
        flag: boot
      - id: sda2
        type: partition
        number: 2
        size: 1GB
        device: disk0
      - id: sda1_root
        type: format
        fstype: ext4
        volume: sda1
      - id: sda2_home
        type: format
        fstype: ext4
        volume: sda2
      - id: sda1_mount
        type: mount
        path: /
        device: sda1_root
      - id: sda2_mount
        type: mount
        path: /home
        device: sda2_home
