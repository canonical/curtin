==========
APT Source
==========

This part of curtin is meant to allow influencing the apt behaviour and configuration.

By default - if no apt config is provided - it does nothing. That keeps behavior compatible on upgrades.

The feature has an optional target argument which - by default - is used to modify the environment that curtin currently installs (@TARGET_MOUNT_POINT).

Features
~~~~~~~~

* Add PGP keys to the APT trusted keyring

  - add via short keyid

  - add via long key fingerprint

  - specify a custom keyserver to pull from

  - add raw keys (which makes you independent of keyservers)

* Influence global apt configuration

  - adding ppa's

  - replacing mirror, security mirror and release in default sources

  - able to provide a fully custom template for default sources

  - add arbitrary apt.conf settings

  - add arbitrary apt preferences

  - provide debconf configurations

  - disabling suites (=pockets)

  - disabling components (multiverse, universe, restricted)

  - per architecture mirror definition


Configuration
~~~~~~~~~~~~~

The general configuration of the apt feature is under an element called ``apt``.

This can have various "global" subelements as listed in the examples below.
The file ``apt-source.yaml`` holds more examples.

These global configurations are valid throughput all of the apt feature.
So for example a global specification of a ``primary`` mirror will apply to all rendered sources entries.

Then there is a section ``sources`` which can hold any number of source subelements itself.
The key is the filename and will be prepended by /etc/apt/sources.list.d/ if it doesn't start with a ``/``.
The filename should be appropriate to the apt source format that is used.
For classic one-line source entries, the ``.list`` extension should be used.
For deb822 source entries, use the ``.sources`` extension.
There are certain cases - where no content is written into a sources file where the filename will be ignored - yet it can still be used as index for merging.

The values inside the entries consist of the following optional entries

* ``source``: an apt source entry, either in classic one-line format, or in deb822 format (some variable replacements apply)

* ``keyid``: providing a key to import via shortid or fingerprint

* ``key``: providing a raw PGP key

* ``keyserver``: specify an alternate keyserver to pull keys from that were specified by keyid

The section "sources" is is a dictionary (unlike most block/net configs which are lists). This format allows merging between multiple input files than a list like ::

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

That would be specified as ::

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

The file `examples/apt-source.yaml <https://github.com/canonical/curtin/blob/master/examples/apt-source.yaml>`_ holds various further examples that can be configured with this feature.

deb822 sources on Ubuntu >= 24.04
---------------------------------

By default, Ubuntu 24.04 and newer use the
`deb822 format for apt sources <https://manpages.ubuntu.com/manpages/en/man5/sources.list.5.html>`_.
When processing the apt configuration for a target system that should use deb822 sources, curtin will migrate legacy one-line sources to deb822 on-the-fly.
The resulting configuration is functionally equivalent, but the sources on the target system will be formatted differently than provided in the configuration.

For example, a configuration snippet that looks like ::

 apt:
   sources:
     proposed.list:
       source: |
         deb http://archive.ubuntu.com/ubuntu/ noble-proposed main restricted universe multiverse

will result in a file on the target system called ``/etc/apt/sources.list.d/proposed.sources`` that looks like ::

 Types: deb
 URIs: http://archive.ubuntu.com/ubuntu/
 Suites: noble-proposed
 Components: main restricted universe multiverse

Common snippets
~~~~~~~~~~~~~~~
This is a collection of additional ideas people can use the feature for customizing their to-be-installed system.

* Enable proposed on installing:

::

 apt:
   sources:
     proposed.list:
       source: |
         deb $MIRROR $RELEASE-proposed main restricted universe multiverse

* Add a PPA:

::

  apt:
    sources:
      curtin-ppa:
        source: ppa:curtin-dev/test-archive


* Make debug symbols available:

::

 apt:
   sources:
     ddebs.list:
       source: |
         deb http://ddebs.ubuntu.com $RELEASE main restricted universe multiverse
         deb http://ddebs.ubuntu.com $RELEASE-updates main restricted universe multiverse
         deb http://ddebs.ubuntu.com $RELEASE-security main restricted universe multiverse
         deb http://ddebs.ubuntu.com $RELEASE-proposed main restricted universe multiverse

* Or, to achieve the same with deb822 sources:

::

 apt:
   sources:
     ddebs.sources:
       source: |
         Types: deb
         URIs: http://ddebs.ubuntu.com
         Suites: $RELEASE $RELEASE-updates $RELEASE-security $RELEASE-proposed
         Components: main restricted universe multiverse

Using templates
~~~~~~~~~~~~~~~

Curtin supports the usage of custom templates for rendering ``sources.list`` or ``ubuntu.sources``.
If a template is not provided, curtin will try to modify the ``sources.list`` (or ``ubuntu.sources`` in the case of deb822) in the target at
``/etc/apt/sources.list`` (or ``/etc/apt/sources.list.d/ubuntu.sources`` in the case of deb822). Within these templates you can use the following
replacement variables: ``$RELEASE, $MIRROR, $PRIMARY, $SECURITY``.

The following example configures ``ubuntu.sources`` in deb822 format, supplies a custom GPG key, and uses the template feature to genericise the configuration across releases.

::

 apt:
   primary:
     - arches: [amd64, i386, default]
       uri: http://mymirror.local/ubuntu
   sources_list: |
     Types: deb
     URIs: $PRIMARY
     Suites: $RELEASE $RELEASE-updates $RELEASE-security $RELEASE-proposed
     Components: main
     Signed-By: # full key as block
       -----BEGIN PGP PUBLIC KEY BLOCK-----
       Version: GnuPG v1
       .
       mQGiBEFEnz8RBAC7LstGsKD7McXZgd58oN68KquARLBl6rjA2vdhwl77KkPPOr3O
       RwIbDAAKCRBAl26vQ30FtdxYAJsFjU+xbex7gevyGQ2/mhqidES4MwCggqQyo+w1
       Twx6DKLF+3rF5nf1F3Q=
       =PBAe
       -----END PGP PUBLIC KEY BLOCK-----

The template above will result in the following ``ubuntu.sources`` file:

::

 Types: deb
 URIs: http://mymirror.local/ubuntu
 Suites: noble noble-updates noble-security noble-backports
 Components: main
 Signed-By: | # full key as block
   -----BEGIN PGP PUBLIC KEY BLOCK-----
   Version: GnuPG v1
   .
   mQGiBEFEnz8RBAC7LstGsKD7McXZgd58oN68KquARLBl6rjA2vdhwl77KkPPOr3O
   RwIbDAAKCRBAl26vQ30FtdxYAJsFjU+xbex7gevyGQ2/mhqidES4MwCggqQyo+w1
   Twx6DKLF+3rF5nf1F3Q=
   =PBAe
   -----END PGP PUBLIC KEY BLOCK-----

The file `examples/apt-source.yaml <https://github.com/canonical/curtin/blob/master/examples/apt-source.yaml>`_ holds more examples on how to use templates. Note that blank lines in the key block should be encoded with leading spaces and "." (see `sources.list(5) <https://manpages.ubuntu.com/manpages/latest/en/man5/sources.list.5.html>`).

Timing
~~~~~~
The feature is implemented at the stage of curthooks_commands, which runs just after curtin has extracted the image to the target.
Additionally it can be ran as standalong command "curtin -v --config <yourconfigfile> apt-config".

This will pick up the target from the environment variable that is set by curtin, if you want to use it to a different target or outside of usual curtin handling you can add ``--target <path>`` to it to overwrite the target path.
This target should have at least a minimal system with apt, apt-add-repository and dpkg being installed for the functionality to work.


Dependencies
~~~~~~~~~~~~
Cloud-init might need to resolve dependencies and install packages in the ephemeral environment to run curtin.
Therefore it is recommended to not only provide an apt configuration to curtin for the target, but also one to the install environment via cloud-init.


apt preserve_sources_list setting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
cloud-init and curtin treat the ``preserve_sources_list`` setting slightly differently, and thus this setting deserves its own section.

Interpretation / Meaning
------------------------
curtin reads ``preserve_sources_list`` to indicate whether or not it should update the target systems' ``/etc/apt/sources.list``.  This includes replacing the mirrors used (apt/primary...).

cloud-init reads ``preserve_sources_list`` to indicate whether or not it should *render* ``/etc/apt/sources.list`` from its built-in template.

defaults
--------
Just for reference, the ``preserve_sources_list`` defaults in curtin and cloud-init are:

 * curtin: **true**
   By default curtin will not modify ``/etc/apt/sources.list`` in the installed OS.  It is assumed that this file is intentionally as it is.
 * cloud-init: **false**
 * cloud-init in ephemeral environment: **false**
 * cloud-init system installed by curtin: **true**
   (curtin writes this to a file ``/etc/cloud/cloud.cfg.d/curtin-preserve-sources.cfg`` in the target).  It does this because we have already written the sources.list that is desired in the installer.  We do not want cloud-init to overwrite it when it boots.

preserve_sources_list in MAAS
-----------------------------
Curtin and cloud-init use the same ``apt`` configuration language.
MAAS provides apt config in three different scenarios.

 1. To cloud-init in ephemeral environment (rescue, install or commissioning)
     Here MAAS **should not send a value**.  If it wants to be explicit it should send ``preserve_sources_list: false``.

 2. To curtin in curtin config
     MAAS **should send ``preserve_sources_list: false``**.  curtin will correctly read and update mirrors in official Ubuntu images, so setting this to 'false' is correct. In some cases for custom images, the user might want to be able to have their /etc/apt/sources.list left untouched entirely.  In such cases they may want to override this value.

 3. To cloud-init via curtin config in debconf_selections.
     MAAS should **not send a value**.  Curtin will handle telling cloud-init to not update /etc/apt/sources.list.  MAAS does not need to do this.

 4. To installed system via vendor-data or user-data.
     MAAS should **not send a value**.  MAAS does not currently send a value.  The user could send one in user-data, but then if they did presumably they did that for a reason.

Legacy format
-------------

Versions of cloud-init in 14.04 and older only support:

.. code-block:: yaml

    apt_preserve_sources_list: VALUE

Versions of cloud-init present 16.04+ read the "new" style apt configuration, but support the old style configuration also.  The new style configuration is:

.. code-block:: yaml

    apt:
      preserve_sources_list: VALUE

**Note**: If versions of cloud-init that support the new style config receive conflicting values in old style and new style, cloud-init will raise exception and exit failure.  It simplly doesn't know what behavior is desired.
