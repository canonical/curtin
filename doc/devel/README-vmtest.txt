== Background ==
Curtin includes a mechanism called 'vmtest' that allows it to actually
do installs and validate a number of configurations.

The general flow of the vmtests is:
 * install a system using 'tools/launch'.  The install environment is
   booted from a maas ephemeral image.
 * configure the installed image to contain a 'NoCloud' datasource seed
   that provides scripts that will run on first boot.
 * power off the system.
 * boot the system with 'tools/xkvm'.  This boot will run the provided
   scripts, write their output to a "data" disk and then shut itself down.
 * extract the data from the data disk and verify the output is as expected.

== Setup ==
In order to run vmtest you'll need some dependencies.  To get them, you 
can run:
  make vmtest-deps

That will install all necessary dependencies.

== Running ==
Running tests is done most simply by:

  make vmtest

If you wish to run a single test, you can run all tests in test_network.py with:
  sudo PATH=$PWD/tools:$PATH nosetests3 tests/vmtests/test_network.py:WilyTestBasic

Or run a single test with:
  sudo PATH=$PWD/tools:$PATH nosetests3 tests/vmtests/test_network.py:WilyTestBasic

Note:
  * currently, the tests have to run as root.  The reason for this is that
    the kernel and initramfs to boot are extracted from the maas ephemeral
    image.  This should be fixed at some point, and then 'make vmtest'

    The tests themselves don't actually have to run as root, but the
    test setup does.
  * the 'tools' directory must be in your path.
