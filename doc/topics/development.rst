=================
Developing Curtin 
=================

Curtin developers make use of cloud-images and kvm to help develop and test new
curtin features.

Install dependencies
====================

Install some virtualization and cloud packages to get started.::

  sudo apt-get -qy install kvm libvirt-bin cloud-utils bzr


Download cloud images
=====================
Curtin will use two cloud images (-disk1.img) is for booting, 
(-root.tar.gz) is used for installing.::

  mkdir -p ~/download
  DLDIR=$( cd ~/download && pwd )
  rel="trusty"
  arch=amd64
  burl="http://cloud-images.ubuntu.com/$rel/current/"
  for f in $rel-server-cloudimg-${arch}-root.tar.gz $rel-server-cloudimg-${arch}-disk1.img; do
    wget "$burl/$f" -O $DLDIR/$f; done
  ( cd $DLDIR && qemu-img convert -O qcow $rel-server-cloudimg-${arch}-disk1.img $rel-server-cloudimg-${arch}-disk1.qcow2)

  export BOOTIMG="$DLDIR/$rel-server-cloudimg-${arch}-disk1.qcow2"
  export ROOTTGZ="$DLDIR/$rel-server-cloudimg-${arch}-root.tar.gz"


Getting the source
==================
Download curtin source from launchpad via `bzr` command.::

  mkdir -p ~/src
  bzr init-repo ~/src/curtin
  ( cd ~/src/curtin && bzr  branch lp:curtin trunk.dist )
  ( cd ~/src/curtin && bzr branch trunk.dist trunk )

Using curtin
============
Use `launch` to launch a kvm instance with user data to pack up
local curtin and run it inside an instance.::

  cd ~/src/curtin/trunk
  ./tools/launch $BOOTIMG --publish $ROOTTGZ -- curtin install "PUBURL/${ROOTTGZ##*/}"


Notes about 'launch'
====================

- launch has --help so you can see that for some info.
- `--publish` adds a web server at ${HTTP_PORT:-$RANDOM_PORT}
  and puts the files you want available there.  You can reference
  this url in config or cmdline with 'PUBURL'.  For example
  `--publish foo.img` will put `foo.img` at PUBURL/foo.img.
- launch sets 'ubuntu' user password to 'passw0rd'
- launch runs 'kvm -curses'
  kvm -curses keyboard info:
  'alt-2' to go to qemu console
- launch puts serial console to 'serial.log' (look there for stuff)
- when logged in
  - you can look at /var/log/cloud-init-output.log
  - archive should be extracted in /curtin
  - shell archive should be in /var/lib/cloud/instance/scripts/part-002
