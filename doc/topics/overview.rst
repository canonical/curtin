========
Overview
========

Curtin is intended to be a bare bones "installer".   Its goal is to take data from a source, and get it onto disk as quick as possible and then boot it.  The key difference from traditional package based installers is that curtin assumes the thing its installing is intelligent and will do the right thing.

Stages
------
A usage of curtin will go through the following stages:

- Install Environment boot
- Early Commands
- Partitioning
- Network Discovery and Setup
- Extraction of sources
- Hook for installed OS to customize itself
- Final Commands

Install Environment boot
~~~~~~~~~~~~~~~~~~~~~~~~
At the moment, curtin doesn't address how the system that it is running on is booted.  It could be booted from a live-cd or from a pxe boot environment.  It could even be booted off a disk in the system (although installation to that disk would probably break things).

Curtin's assumption is that a fairly rich Linux (Ubuntu) environment is booted.

Early Commands
~~~~~~~~~~~~~~
Early commands are executed on the system, and non-zero exit status will terminate the installation process.  These commands are intended to be used for things like

- module loading
- hardware setup
- environment setup for subsequent stages of curtin.

**Config Example**::

 early_commands:
  05_load_loop: [modprobe, loop]
  99_update: apt-get update && apt-get dist-upgrade

Partitioning
~~~~~~~~~~~~
Partitioning covers setting up filesystems on the system.  A series of commands are run serially in order.  At the end, a fstab formatted file must be populated in ``OUTPUT_FSTAB`` that contains mount information, and the filesystems are expected to be mounted at the ``TARGET_MOUNT_POINT``.

Any commands can be used to create this filesystem, but curtin contains some tools to facilitate with this process.

**Config Example**::

 partitioning_commands:
  10_wipe_filesystems: curtin wipe --quick --all-unused-disks
  50_setup_raid: curtin disk-setup --all-disks raid0 /

**Command environment**

Partitioning commands have the following environment variables available to them:

- ``WORKING_DIR``: This is simply for some sort of inter-command state.  It will be the same directory for each command run and will only be deleted at the end of all partitioning_commands.
- ``OUTPUT_FSTAB``: This is the target path for a fstab file.  After all partitioning commands have been run, a file should exist, formatted per fstab(5) that describes how the filesystems should be mounted.
- ``TARGET_MOUNT_POINT``:


Network Discovery and Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Networking is done in a similar fashion to partitioning.  A series of commands, specified in the config are run.  At the end of these commands, a interfaces(5) style file is expected to be written to ``OUTPUT_INTERFACES``.

Note, that as with fstab, this file is not copied verbatim to the target filesystem, but rather made available to the OS customization stage.  That stage may just copy the file verbatim, but may also parse it, and use that as input.

**Config Example**::

 network_commands:
  10_netconf: curtin network copy-existing

**Command environment**

Networking commands have the following environment variables available to them:

- ``WORKING_DIR``: This is simply for some sort of inter-command state.  It will be the same directory for each command run and will only be deleted at the end of all network_commands.
- ``OUTPUT_INTERFACES``: This is the target path for an interfaces style file. After all commands have been run, a file should exist, formatted per interfaces(5) that describes the systems network setup.

Extraction of sources
~~~~~~~~~~~~~~~~~~~~~
Sources are the things to install.  Curtin prefers to install root filesystem tar files.

**Config Example**::

 sources:
  05_primary: http://cloud-images.ubuntu.com/releases/precise/release/ubuntu-12.04-server-cloudimg-amd64-root.tar.gz

Given the source above, curtin will essentially do a::

 wget $URL | tar -Sxvzf 

Hook for installed OS to customize itself
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
After extraction of sources, the source that was extracted is then given a chance to customize itself for the system.  This customization may include:
 - ensuring that appropriate device drivers are loaded on first boot
 - consuming the network interfaces file and applying its declarations.
 - ensuring that necessary packages 

**Config Example**::

 config_hook: {{TARGET_MP}}/opt/curtin/config-hook

**Command environment**
 - ``INTERFACES``: This is a path to the file created during networking stage
 - ``FSTAB``: This is a path to the file created during partitioning stage
 - ``CONFIG``: This is a path to the curtin config file.  It is provided so that additional configuration could be provided through to the OS customization.

**Helpers**

Curtin provides some helpers to make the OS customization easier.
 - `curtin in-target`: run the command while chrooted into the target.

Final Commands
~~~~~~~~~~~~~~

**Config Example**::

 final_commands:
  05_callhome_finished: wget http://example.com/i-am-done
