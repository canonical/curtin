==========
APT Source
==========

This part of curtin is meant to allow influencing the apt behaviour and configuration.

By default - if no apt config is provided - it does nothing. That keeps behavior compatible on upgrades.

The feature has an optional target argument which - by default - is used to modify the environment that curtin currently installs (@TARGET_MOUNT_POINT).

Features
--------

* Add PGP keys to the APT trusted keyring

  - add via short keyid

  - add via long key fingerprint

  - specify a custom keyserver to pull from

  - add raw keys (which makes you independent of keyservers)

* Influence global apt configuration

  - adding ppa's

  - replacing mirror, security mirror and release in sources.list

  - able to provide a fully custom template for sources.list

  - add arbitrary apt.conf settings

  - provide debconf configurations

  - disabling suites (=pockets)

  - per architecture mirror definition


Configuration
-------------

The general configuration of the apt feature is under an element called ``apt``.

This can have various "global" subelements as listed in the examples below.
The file ``apt-source.yaml`` holds more examples.

These global configurations are valid throughput all of the apt feature.
So for exmaple a global specification of a ``primary`` mirror will apply to all rendered sources entries.

Then there is a section ``sources`` which can hold any number of source subelements itself.
The key is the filename and will be prepended by /etc/apt/sources.list.d/ if it doesn't start with a ``/``.
There are certain cases - where no content is written into a source.list file where the filename will be ignored - yet it can still be used as index for merging.

The values inside the entries consist of the following optional entries::
* ``source``: a sources.list entry (some variable replacements apply)

* ``keyid``: providing a key to import via shortid or fingerprint

* ``key``: providing a raw PGP key

* ``keyserver``: specify an alternate keyserver to pull keys from that were specified by keyid

The section "sources" is is a dictionary (unlike most block/net configs which are lists). This format allows merging between multiple input files than a list like::
  sources:
     s1: {'key': 'key1', 'source': 'source1'}

  sources:
     s2: {'key': 'key2'}
     s1: {'keyserver': 'foo'}

  This would be merged into
     s1: {'key': 'key1', 'source': 'source1', keyserver: 'foo'}
     s2: {'key': 'key2'}

Here is just one of the most common examples for this feature: install with curtin in an isolated environment (derived repository):

For that we need to:
* insert the PGP key of the local repository to be trusted

  - since you are locked down you can't pull from keyserver.ubuntu.com

  - if you have an internal keyserver you could pull from there, but let us assume you don't even have that; so you have to provide the raw key

  - in the example I'll use the key of the "Ubuntu CD Image Automatic Signing Key" which makes no sense as it is in the trusted keyring anyway, but it is a good example. (Also the key is shortened to stay readable)

::

      -----BEGIN PGP PUBLIC KEY BLOCK-----
      Version: GnuPG v1
      mQGiBEFEnz8RBAC7LstGsKD7McXZgd58oN68KquARLBl6rjA2vdhwl77KkPPOr3O
      RwIbDAAKCRBAl26vQ30FtdxYAJsFjU+xbex7gevyGQ2/mhqidES4MwCggqQyo+w1
      Twx6DKLF+3rF5nf1F3Q=
      =PBAe
      -----END PGP PUBLIC KEY BLOCK-----

* replace the mirrors used to some mirrors available inside the isolated environment for apt to pull repository data from.

  - lets consider we have a local mirror at ``mymirror.local`` but otherwise following the usual paths

  - make an example with a partial mirror that doesn't mirror the backports suite, so backports have to be disabled

That would be specified as
::

  apt:
    primary:
      - arches [default]
        uri: http://mymirror.local/ubuntu/
    disable_suites: [backports]
    sources:
      localrepokey:
        key: | # full key as block
          -----BEGIN PGP PUBLIC KEY BLOCK-----
          Version: GnuPG v1

          mQGiBEFEnz8RBAC7LstGsKD7McXZgd58oN68KquARLBl6rjA2vdhwl77KkPPOr3O
          RwIbDAAKCRBAl26vQ30FtdxYAJsFjU+xbex7gevyGQ2/mhqidES4MwCggqQyo+w1
          Twx6DKLF+3rF5nf1F3Q=
          =PBAe
          -----END PGP PUBLIC KEY BLOCK-----

The file examples/apt-source.yaml holds various further examples that can be configured with this feature.


Common snippets
---------------
This is a collection of additional ideas people can use the feature for customizing their to-be-installed system.

* enable proposed on installing
  apt:
    sources:
      proposed.list: deb $MIRROR $RELEASE-proposed main restricted universe multiverse

* Make debug symbols available
  apt:
    sources:
      ddebs.list: |
        deb http://ddebs.ubuntu.com $RELEASE main restricted universe multiverse
        deb http://ddebs.ubuntu.com $RELEASE-updates main restricted universe multiverse
        deb http://ddebs.ubuntu.com $RELEASE-security main restricted universe multiverse
        deb http://ddebs.ubuntu.com $RELEASE-proposed main restricted universe multiverse


Timing
------
The feature is implemented at the stage of curthooks_commands, which runs just after curtin has extracted the image to the target.
Additionally it can be ran as standalong command "curtin -v --config <yourconfigfile> apt-config".

This will pick up the target from the environment variable that is set by curtin, if you want to use it to a different target or outside of usual curtin handling you can add ``--target <path>`` to it to overwrite the target path.
This target should have at least a minimal system with apt, apt-add-repository and dpkg being installed for the functionality to work.


Dependencies
------------
Cloud-init might need to resolve dependencies and install packages in the ephemeral environment to run curtin.
Therefore it is recommended to not only provide an apt configuration to curtin for the target, but also one to the install environment via cloud-init.
