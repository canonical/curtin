========================================
Curthooks / New Operating System Support 
========================================
Curtin has built-in support for installation of Ubuntu.
Other operating systems are supported through a mechanism called
'curthooks' or 'curtin-hooks'.

A curtin install runs through different stages.  See the 
:ref:`Stages <stages>`
documentation for function of each stage.
The stages communicate with each other via data in a working working
directory and environment variables as described in
:ref:`Command Environment`.

Curtin handles partitioning, filesystem creation and target filesystem
population for all operating systems. Curthooks are the mechanism provided
so that the operating system can customize itself before reboot. This
customization typically would need to include:

 - ensuring that appropriate device drivers are loaded on first boot
 - consuming the network interfaces file and applying its declarations.
 - ensuring that necessary packages are installed to utilize storage
   configuration or networking configuration.
 - making the system boot (running grub-install or equivalent).

Image provided curtin-hooks
---------------------------
An image provides curtin hooks support by containing a file
`/curtin/curtin-hooks`.

If an Ubuntu image image contains this path it will override the builtin
curtin support.

The `curtin-hooks` program should be executable in the filesystem and
will be executed without any arguments.  It will be executed in the install
environment, *not* the target environment.  A change of root to the
target environment can be done with `curtin in-target`.

The hook is provided with some environment variables that can be used
to find more information.

 - ``INTERFACES``: This is a path to the file created during networking stage
 - ``FSTAB``: This is a path to the file created during partitioning stage
 - ``CONFIG``: This is a path to the curtin config file.  It is provided so
   that additional configuration could be provided through to the OS
   customization.

**TODO**: We should add 'PYTHON' or 'CURTIN_PYTHON' to this environment
so that the hook can easily run a python program with the same python
that curtin ran with (ie, python2 or python3).


Networking configuration
------------------------
Access to the network configuration that is desired is inside the config
and is in the format described in :ref:`networking`_.

The curtin-hooks program must read this configuration and then set up
the installed system to use it.

If the installed system has cloud-init at version 17.1 or higher, it may
be possible to simply copy this section into the target in
``/etc/cloud/cloud.cfg.d/`` and let cloud-init render the correct
networking on first boot.

Storage configuration
---------------------
Access to the storage configuration that was set up is inside the config
and is in the format described in :ref:`storage`_.

To apply this storage configuration, the curthooks may need to:

 * update /etc/fstab to add the expected mounts entries.  The environment
   variable ``FSTAB`` contains a path to a file that may be suitable
   for use.

 * install any packages that are not already installed that are required
   to boot with the provided storage config.  For example, if the storage
   layout includes raid you may need to install the mdadm package.

 * update or create an initramfs.


System boot
-----------
In Ubuntu, curtin will run 'grub-setup' and to install grub.  This covers
putting the bootloader onto the disk(s) that are marked as
``grub_device``.  The provided hook will need to do the equivalent
operation.

finalize hook
-------------
There is one other hook that curtin will invoke in an install, called
``finalize``.  This program is invoked in the same environment as
``curtin-hooks`` above.  It is intended to give the OS a final opportunity
make updates before reboot.  It is called before ``late_commands``.
