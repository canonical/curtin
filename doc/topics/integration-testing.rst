===================
Integration Testing
===================

Curtin includes an in-tree integration suite that runs hundreds of tests
validating various forms of custom storage and network configurations across
all of the supported Ubuntu LTS releases as well as some of the currently 
supported interim releases.

Background
==========

Curtin includes a mechanism called 'vmtest' that allows it to actually
do installs and validate a number of configurations.

The general flow of the vmtests is:

#. each test has an associated yaml config file for curtin in examples/tests
#. uses curtin-pack to create the user-data for cloud-init to trigger install
#. create and install a system using 'tools/launch'.

   #. The install environment is booted from a maas ephemeral image.
   #. kernel & initrd used are from maas images (not part of the image)
   #. network by default is handled via user networking
   #. It creates all empty disks required
   #. cloud-init datasource is provided by launch

      #. like: ds=nocloud-net;seedfrom=http://10.7.0.41:41518/
         provided by python webserver start_http
      #. via -drive file=/tmp/launch.8VOiOn/seed.img,if=virtio,media=cdrom
         as a seed disk (if booted without external kernel)

   #. dependencies and other preparations are installed at the beginning by
      curtin inside the ephemeral image prior to configuring the target

#. power off the system.
#. configure a 'NoCloud' datasource seed image that provides scripts that
   will run on first boot.

   #. this will contain all our code to gather health data on the install
   #. by cloud-init design this runs only once per instance, if you start
      the system again this won't be called again

#. boot the installed system with 'tools/xkvm'.

   #. reuses the disks that were installed/configured in the former steps
   #. also adds an output disk
   #. additionally the seed image for the data gathering is added
   #. On this boot it will run the provided scripts, write their output to a
      "data" disk and then shut itself down.

#. extract the data from the output disk
#. vmtest python code now verifies if the output is as expected.

Debugging
=========

At 3.1 one can pull data out of the maas image the command 
``mount-image-callback``.  For example::

  sudo mount-image-callback your.img -- sh -c 'cp $MOUNTPOINT/boot/* .'

At step 3.6 through 4 ``tools/launch`` can be called in a way to give you
console access.  To do so just call tools/launch but drop the -serial=x
parameter.  One might want to change "'power_state': {'mode': 'poweroff'}" to
avoid the auto reboot before getting control.  Replace the directory usually
seen in the launch calls with a clean fresh directory.

In /curtin curtin and its config can be found. If the system gets that far
cloud-init will create a user creds: ubuntu/passw0rd , otherwise one can use a
cloud-image from  https://cloud-images.ubuntu.com/ and add a backdoor user
via::

  bzr branch lp:~maas-maintainers/maas/backdoor-image backdoor-image
  sudo ./backdoor-image -v --user=<USER> --password-auth --password=<PW> IMG

At step 6 -> 7 you might want to keep all the temporary images around.  To do
so you can set ``CURTIN_VMTEST_KEEP_DATA_PASS=all`` in your environment. ::

  export CURTIN_VMTEST_KEEP_DATA_PASS=all CURTIN_VMTEST_KEEP_DATA_FAIL=all

That will keep the /tmp/tmpXXXXX directories and all files in there for further
execution.

At step 7 you might want to take a look at the output disk yourself.  It is a
normal qcow image, so one can use ``mount-image-callback`` as described above.

To invoke xkvm on your own take the command you see in the output and remove
the "-serial ..." but add ``-nographic`` instead For graphical console one can
add ``--vnc 127.0.0.1:1``

Setup
=====

In order to run vmtest you'll need some dependencies.  To get them, you 
can run::

  make vmtest-deps

Running
=======

Running tests is done most simply by::

  make vmtest

If you wish to all tests in test_network.py, do so with::

  nosetests3 tests/vmtests/test_network.py

Or run a single test with::

  nosetests3 tests/vmtests/test_network.py:WilyTestBasic


Environment Variables
=====================

Some environment variables affect the running of vmtest

- ``apt_proxy``:

    test will set apt: { proxy } in the guests to the value of ``apt_proxy``
    environment variable.  If that is not set it will look at the host's apt
    config and read ``Acquire::HTTP::Proxy``

- ``CURTIN_VMTEST_KEEP_DATA_PASS``: Defaults to none.
- ``CURTIN_VMTEST_KEEP_DATA_FAIL``: Defaults to all.

  These 2 variables determine what portions of the temporary
  test data are kept.

  The variables contain a comma ',' delimited list of directories
  that should be kept in the case of pass or fail.  Additionally,
  the values 'all' and 'none' are accepted.

  Each vmtest that runs has its own sub-directory under the top level
  ``CURTIN_VMTEST_TOPDIR``.  In that directory are directories:

    - ``boot``: inputs to the system boot (after install)
    - ``install``: install phase related files
    - ``disks``: the disks used for installation and boot
    - ``logs``: install and boot logs
    - ``collect``: data collected by the boot phase

- ``CURTIN_VMTEST_TOPDIR``: default $TMPDIR/vmtest-<timestamp>

  Vmtest puts all test data under this value.  By default, it creates
  a directory in TMPDIR (/tmp) named with as ``vmtest-<timestamp>``

  If you set this value, you must ensure that the directory is either
  non-existent or clean.

- ``CURTIN_VMTEST_LOG``: default $TMPDIR/vmtest-<timestamp>.log

  Vmtest writes extended log information to this file.
  The default puts the log along side the TOPDIR.

- ``CURTIN_VMTEST_IMAGE_SYNC``: default false (boolean)

  If set to true, each run will attempt a sync of images.
  If you want to make sure images are always up to date, then set to true.

- ``CURTIN_VMTEST_BRIDGE``: ``user``

  The network devices will be attached to this bridge.  The default is
  ``user``, which means to use qemu user mode networking.  Set it to
  ``virbr0`` or ``lxdbr0`` to use those bridges and then be able to ssh
  in directly.

- ``CURTIN_VMTEST_BOOT_TIMEOUT``: default 300

    timeout before giving up on the boot of the installed system.

- ``CURTIN_VMTEST_INSTALL_TIMEOUT``: default 3000

    timeout before giving up on installation.

- ``CURTIN_VMTEST_PARALLEL``: default ''

    only supported through ./tools/jenkins-runner .

    - ``-1``: then run one per core.
    - ``0`` or ``''``: run with no parallel
    - ``>0``: run with N processes

    This modifies the  invocation of nosetets to add '--processes' and other
    necessary nose arguments (--process-timeout)

- ``IMAGE_DIR``: default /srv/images

  Vmtest keeps a mirror of maas ephemeral images in this directory.

- ``IMAGES_TO_KEEP``: default 1

  Controls the number of images of each release retained in the IMAGE_DIR.

Environment 'boolean' values
============================

For boolean environment variables the value is considered True
if it is any value other than case insensitive 'false', '' or "0".

Test Class Variables
====================

The base VMBaseClass defines several variables that help creating a new test
easily. Among those the common ones are:

Generic:

- ``arch_skip``: 

  If a test is not supported on an architecture it can list the arch in this
  variable to auto-skip the test if executed on that arch.

- ``conf_file``:

  The configuration that will be processed by this vmtest.

- ``extra_kern_args``:

  Extra arguments to the guest kernel on boot.

Data Collection:

- ``collect_scripts``:

  The commands run when booting into the installed environment to collect the
  data for the test to verify a proper execution.

- ``boot_cloudconf``:

  Extra cloud-init config content for the install phase.  This allows to gather
  content of the install phase if needed for test verification.

Disk Setup:

- ``disk_block_size``:

  Default block size ``512`` bytes.

- ``disk_driver``:

  Default block device driver is ``virtio-blk``.
