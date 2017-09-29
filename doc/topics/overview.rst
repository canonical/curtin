========
Overview
========

Curtin is intended to be a bare bones "installer".   Its goal is to take data from a source, and get it onto disk as quick as possible and then boot it.  The key difference from traditional package based installers is that curtin assumes the thing its installing is intelligent and will do the right thing.

.. _Stages:

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

.. _Command Environment:

Command Environment
~~~~~~~~~~~~~~~~~~~
Stages and commands invoked by curtin always have the following environment
variables defined.

- ``WORKING_DIR``: This is for inter-command state.  It will be the same
  directory for each command run and will only be deleted at the end of the
  install. Files referenced in other environment variables will be in
  this directory.

- ``TARGET_MOUNT_POINT``: The path in the filesystem where the target
  filesystem will be mounted.

- ``OUTPUT_NETWORK_CONFIG``: After the network discovery stage, this file
  should contain networking config information that should then be written
  to the target.

- ``OUTPUT_FSTAB``: After partitioning and filesystem creation, this file
  will contain fstab(5) style content representing mounts.

- ``CONFIG``: This variable contains a path to a yaml formatted file with
  the fully rendered config.


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


Network Discovery
~~~~~~~~~~~~~~~~~
Networking configuration is *discovered* in the 'network' stage.
The default command run at this stage is ``curtin net-meta auto``.  After
execution, it will write the discovered networking to the file specified
in the environment variable ``OUTPUT_NETWORK_CONFIG``.  The format of this
file is as described in :ref:`networking`.

If curtin's config has a network section, the net-meta will simply parrot the
data to the output file.  If there is no network section, then its default
behavior is to copy existing config from the running environment.

Note, that as with fstab, this file is not copied verbatim to the target
filesystem, but rather made available to the OS customization stage.  That
stage may just copy the file verbatim, but may also parse it, and apply the
settings.

Extraction of sources
~~~~~~~~~~~~~~~~~~~~~
Sources are the things to install.  Curtin prefers to install root filesystem tar files.

**Config Example**::

 sources:
  05_primary: http://cloud-images.ubuntu.com/releases/precise/release/ubuntu-12.04-server-cloudimg-amd64-root.tar.gz

Given the source above, curtin will essentially do a::

 wget $URL | tar -Sxvzf 

Final Commands
~~~~~~~~~~~~~~

**Config Example**::

 final_commands:
  05_callhome_finished: wget http://example.com/i-am-done
