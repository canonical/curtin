.. _curthooks:

========================================
Curthooks / New OS Support
========================================
Curtin has built-in support for installation of:

 - Ubuntu
 - Centos

Other operating systems are supported through a mechanism called
'curthooks' or 'curtin-hooks'.

A curtin install runs through different stages.  See the 
:ref:`Stages <stages>`
documentation for function of each stage.
The stages communicate with each other via data in a working directory and
environment variables as described in
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
``/curtin/curtin-hooks``.

If an Ubuntu image image contains this path it will override the builtin
curtin support.

The ``curtin-hooks`` program should be executable in the filesystem and
will be executed without any arguments.  It will be executed in the install
environment, *not* the target environment.  A change of root to the
target environment can be done with ``curtin in-target``.

The hook is provided with some environment variables that can be used
to find more information.  See the :ref:`Command Environment` doc for
details.  Specifically interesting to this stage are:

 - ``OUTPUT_NETWORK_CONFIG``: This is a path to the file created during
   network discovery stage. 
 - ``OUTPUT_FSTAB``: This is a path to the file created during partitioning
   stage.
 - ``CONFIG``: This is a path to the curtin config file.  It is provided so
   that additional configuration could be provided through to the OS
   customization.
 - ``WORKING_DIR``: This is a path to a temporary directory where curtin
   stores state and configuration files.

.. **TODO**: We should add 'PYTHON' or 'CURTIN_PYTHON' to this environment
   so that the hook can easily run a python program with the same python
   that curtin ran with (ie, python2 or python3).

Running built-in hooks
----------------------

Curthooks may opt to run the built-in curthooks that are already provided in
curtin itself.  To do so, an in-image curthook can import the ``curthooks``
module and invoke the ``builtin_curthooks`` function passing in the required
parameters: config, target, and state.


Networking configuration
------------------------
Access to the network configuration that is desired is inside the config
and is in the format described in :ref:`networking`.

.. TODO: We should guarantee that the presence
         of network config v1 in the file OUTPUT_NETWORK_CONFIG.

The curtin-hooks program must read the configuration from the
path contained in ``OUTPUT_NETWORK_CONFIG`` and then set up
the installed system to use it.

If the installed system has cloud-init at version 17.1 or higher, it may
be possible to simply copy this section into the target in
``/etc/cloud/cloud.cfg.d/`` and let cloud-init render the correct
networking on first boot.

Storage configuration
---------------------
Access to the storage configuration that was set up is inside the config
and is in the format described in :ref:`storage`.

.. TODO: We should guarantee that the presence
         of storage config v1 in the file OUTPUT_STORAGE_CONFIG.
         This would mean the user would not have to pull it out
         of CONFIG.  We should guarantee its presence and format
         even in the 'simple' path.

To apply this storage configuration, the curthooks may need to:

 * update /etc/fstab to add the expected mounts entries.  The environment
   variable ``OUTPUT_FSTAB`` contains a path to a file that may be suitable
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
