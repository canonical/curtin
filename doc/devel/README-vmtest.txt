== Background ==
Curtin includes a mechanism called 'vmtest' that allows it to actually
do installs and validate a number of configurations.

The general flow of the vmtests is:
 1. each test has an associated yaml config file for curtin in examples/tests
 2. uses curtin-pack to create the user-data for cloud-init to trigger install
 3. create and install a system using 'tools/launch'.
    3.1 The install environment is booted from a maas ephemeral image.
    3.2 kernel & initrd used are from maas images (not part of the image)
    3.3 network by default is handled via user networking
    3.4 It creates all empty disks required
    3.5 cloud-init datasource is provided by launch
      a) like: ds=nocloud-net;seedfrom=http://10.7.0.41:41518/
         provided by python webserver start_http
      b) via -drive file=/tmp/launch.8VOiOn/seed.img,if=virtio,media=cdrom
         as a seed disk (if booted without external kernel)
    3.6 dependencies and other preparations are installed at the beginning by
        curtin inside the ephemeral image prior to configuring the target
 4. power off the system.
 5. configure a 'NoCloud' datasource seed image that provides scripts that
    will run on first boot.
    5.1 this will contain all our code to gather health data on the install
    5.2 by cloud-init design this runs only once per instance, if you start
        the system again this won't be called again
 6. boot the installed system with 'tools/xkvm'.
    6.1 reuses the disks that were installed/configured in the former steps
    6.2 also adds an output disk
    6.3 additionally the seed image for the data gathering is added
    6.4 On this boot it will run the provided scripts, write their output to a
        "data" disk and then shut itself down.
 7. extract the data from the output disk
 8. vmtest python code now verifies if the output is as expected.

== Debugging ==
At 3.1
  - one can pull data out of the maas image with
    sudo mount-image-callback your.img -- sh -c 'COMMAND'
    e.g. sudo mount-image-callback your.img -- sh -c 'cp $MOUNTPOINT/boot/* .'
At step 3.6 -> 4.
  - tools/launch can be called in a way to give you console access
    to do so just call tools/launch but drop the -serial=x parameter.
    One might want to change "'power_state': {'mode': 'poweroff'}" to avoid
    the auto reboot before getting control
    Replace the directory usually seen in the launch calls with a clean fresh
    directory
  - In /curtin curtin and its config can be found
  - if the system gets that far cloud-init will create a user ubuntu/passw0rd
  - otherwise one can use a cloud-image from  https://cloud-images.ubuntu.com/
    and add a backdoor user via
    bzr branch lp:~maas-maintainers/maas/backdoor-image backdoor-image
    sudo ./backdoor-image -v --user=<USER> --password-auth --password=<PW> IMG
At step 6 -> 7
  - You might want to keep all the temporary images around.
    To do so you can set CURTIN_VMTEST_KEEP_DATA_PASS=all:
    export CURTIN_VMTEST_KEEP_DATA_PASS=all CURTIN_VMTEST_KEEP_DATA_FAIL=all
    That will keep the /tmp/tmpXXXXX directories and all files in there for
    further execution.
At step 7
  - You might want to take a look at the output disk yourself.
    It is a normal qcow image, so one can use mount-image-callback as described
    above
  - to invoke xkvm on your own take the command you see in the output and
    remove the "-serial ..." but add -nographic instead
    For graphical console one can add --vnc 127.0.0.1:1

== Setup ==
In order to run vmtest you'll need some dependencies.  To get them, you 
can run:
  make vmtest-deps

That will install all necessary dependencies.

== Running ==
Running tests is done most simply by:

  make vmtest

If you wish to all tests in test_network.py, do so with:
  sudo PATH=$PWD/tools:$PATH nosetests3 tests/vmtests/test_network.py

Or run a single test with:
  sudo PATH=$PWD/tools:$PATH nosetests3 tests/vmtests/test_network.py:WilyTestBasic

Note:
  * currently, the tests have to run as root.  The reason for this is that
    the kernel and initramfs to boot are extracted from the maas ephemeral
    image.  This should be fixed at some point, and then 'make vmtest'

    The tests themselves don't actually have to run as root, but the
    test setup does.
  * the 'tools' directory must be in your path.
  * test will set apt_proxy in the guests to the value of
    'apt_proxy' environment variable.  If that is not set it will 
    look at the host's apt config and read 'Acquire::HTTP::Proxy'

== Environment Variables ==
Some environment variables affect the running of vmtest
  * apt_proxy: 
    test will set apt_proxy in the guests to the value of 'apt_proxy'.
    If that is not set it will look at the host's apt config and read
    'Acquire::HTTP::Proxy'

  * CURTIN_VMTEST_KEEP_DATA_PASS CURTIN_VMTEST_KEEP_DATA_FAIL:
    default:
      CURTIN_VMTEST_KEEP_DATA_PASS=none
      CURTIN_VMTEST_KEEP_DATA_FAIL=all
    These 2 variables determine what portions of the temporary
    test data are kept.

    The variables contain a comma ',' delimited list of directories
    that should be kept in the case of pass or fail.  Additionally,
    the values 'all' and 'none' are accepted.

    Each vmtest that runs has its own sub-directory under the top level
    CURTIN_VMTEST_TOPDIR.  In that directory are directories:
      boot: inputs to the system boot (after install)
      install: install phase related files
      disks: the disks used for installation and boot
      logs: install and boot logs
      collect: data collected by the boot phase

  * CURTIN_VMTEST_TOPDIR: default $TMPDIR/vmtest-<timestamp>
    vmtest puts all test data under this value.  By default, it creates
    a directory in TMPDIR (/tmp) named with as "vmtest-<timestamp>"

    If you set this value, you must ensure that the directory is either
    non-existant or clean.

  * CURTIN_VMTEST_LOG: default $TMPDIR/vmtest-<timestamp>.log
    vmtest writes extended log information to this file.
    The default puts the log along side the TOPDIR.

  * CURTIN_VMTEST_IMAGE_SYNC: default false (boolean)
    if set to true, each run will attempt a sync of images.
    If you want to make sure images are always up to date, then set to true.

  * CURTIN_VMTEST_BRIDGE: default 'user'
    the network devices will be attached to this bridge.  The default is
    'user', which means to use qemu user mode networking.  Set it to
    'virbr0' or 'lxcbr0' to use those bridges and then be able to ssh
    in directly.

  * IMAGE_DIR: default /srv/images
    vmtest keeps a mirror of maas ephemeral images in this directory.

  * IMAGES_TO_KEEP: default 1
    keep this number of images of each release in the IMAGE_DIR.

Environment 'boolean' values:
   For boolean environment variables the value is considered True
   if it is any value other than case insensitive 'false', '' or "0"
