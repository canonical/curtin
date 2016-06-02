==========
APT Source
==========

This part of curtin is meant to allow influencing the apt behaviour in the curtin install stage.

By default - if no apt_source config is provided - it does nothing. That keeps behavior compatible on upgrades.

It is not meant to carry over into the installed environment. For that there is a similar feature in cloud-init which can be exploited via seeds for cloud-init as already done by clouds, MAAS and others.

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


Configuration
-------------

The general configuration is under an element called ``apt_source``.

This can have various global subelements as listed in the examples below - for example ``apt_primary_mirror: http://us.archive.ubuntu.com/ubuntu/``. These global configurations are valid throughput all of the apt_source feature.

Then there is a section ``sources`` which can hold a number of subelements itself.
The key is the filename and will be prepended by /etc/apt/sources.list.d/ if it doesn't start with a ``/``.
There are certain cases - where no content is written into a source.list file where the filename will be ignored - yet it can still be used as index for merging.

The values inside the entries consist of the following optional entries::
* ``source``: a sources.list entry (some variable replacements apply)

* ``keyid``: providing a key to import via shortid or fingerprint

* ``key``: providing a raw PGP key

* ``keyserver``: specify an alternate keyserver to pull keys from that were specified by keyid

* ``filename``: for compatibility with the older format (now the key to this dictionary is the filename). If specified this overwrites the filename given as key.

The section "sources" is is a dictionary (unlike most block/net configs which are lists). This format allows merging between multiple input files than a list like::
  sources:
     s1: {'key': 'key1', 'source': 'source1'}

  sources:
     s2: {'key': 'key2'}
     s1: {'filename': 'foo'}

  This would be merged into
     s1: {'key': 'key1', 'source': 'source1', filename: 'foo'}
     s2: {'key': 'key2'}

Here is just one of the most common examples that could be used to install with curtin in a closed environment (derived repository):

What do we need for that:
* insert the PGP key of the local repository to be trusted

  - since you are locked down you can't pull from keyserver.ubuntu.com

  - if you have an internal keyserver you could pull from there, but let us assume you don't even have that; so you have to provide the raw key

  - in the example I'll use the key of the "Ubuntu CD Image Automatic Signing Key" which makes no sense as it is in the trusted keyring anyway, but it is a good example. (Also the key is shortened to stay readable)::
    -----BEGIN PGP PUBLIC KEY BLOCK-----
    Version: GnuPG v1

    mQGiBEFEnz8RBAC7LstGsKD7McXZgd58oN68KquARLBl6rjA2vdhwl77KkPPOr3O
    RwIbDAAKCRBAl26vQ30FtdxYAJsFjU+xbex7gevyGQ2/mhqidES4MwCggqQyo+w1
    Twx6DKLF+3rF5nf1F3Q=
    =PBAe
    -----END PGP PUBLIC KEY BLOCK-----

* replace the mirror from apt pulls repository data

  - lets consider we have a local mirror at ``mymirror.local`` but otherwise following the usual paths

That would be specified as::
  apt_source:
    version: 1
    apt_mirror: http://mymirror.local/ubuntu/
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

Timing
------
The feature is implemented at the stage of the early commands to be ready in the install environment for any stage following.

It is called by a early_commands builtin.
As mentioned before it does nothing if not explicitly configured, but if there is ever the need to even disable that one could overwrite that builtin like:

network_commands:
  builtin: null
  10_yourcmd: whatever you wanted instead
