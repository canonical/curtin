## curtin development ##

This document describes how to use kvm and ubuntu cloud images
to develop curtin or test install configurations inside kvm.

## get some dependencies ##
sudo apt-get -qy install kvm libvirt-bin cloud-utils bzr

## get cloud image to boot (-disk1.img) and one to install (-root.tar.gz)
mkdir -p ~/download
DLDIR=$( cd ~/download && pwd )
rel="precise"
rel="raring"
burl="http://cloud-images.ubuntu.com/$rel/current/"
for f in $rel-server-cloudimg-amd64-root.tar.gz $rel-server-cloudimg-amd64-disk1.img; do
  wget "$burl/$f" -O $DLDIR/$f; done
( cd $DLDIR && qemu-img convert -O qcow $rel-server-cloudimg-amd64-disk1.img $rel-server-cloudimg-amd64-disk1.qcow2)

BOOTIMG="$DLDIR/$rel-server-cloudimg-amd64-disk1.qcow2"
ROOTTGZ="$DLDIR/$rel-server-cloudimg-amd64-root.tar.gz"

## get curtin
mkdir -p ~/src
bzr init-repo ~/src/curtin
( cd ~/src/curtin && bzr  branch lp:curtin trunk.dist )
( cd ~/src/curtin && bzr branch trunk.dist trunk )

## get xkvm
mkdir -p ~/bin/
wget "http://sn.im/xkvm" -O ~/bin/xkvm
chmod 755 ~/bin/xkvm
which xkvm || PATH=$HOME/bin:$PATH

## work with curtin
cd ~/src/curtin/trunk
# use 'launch' to launch a kvm instance with user data to pack
# up local curtin and run it inside instance.
./tools/launch $BOOTIMG --publish $ROOTTGZ -- curtin install "PUBURL/${ROOTTGZ##*/}"

## notes about 'launch' ##
 * launch has --help so you can see that for some info.
 * '--publish' adds a web server at ${HTTP_PORT:-9923}
   and puts the files you want available there.  You can reference
   this url in config or cmdline with 'PUBURL'.  For example
   '--publish foo.img' will put 'foo.img' at PUBURL/foo.img.
 * launch sets 'ubuntu' user password to 'passw0rd'
 * launch runs 'kvm -curses'
   kvm -curses keyboard info:
     'alt-2' to go to qemu console
 * launch puts serial console to 'serial.log' (look there for stuff)
 * when logged in
   * you can look at /var/log/cloud-init-output.log
   * archive should be extracted in /curtin
   * shell archive should be in /var/lib/cloud/instance/scripts/part-002
 * when logged in, and archive available at


## other notes ##
 * need to add '--install-deps' or something for curtin
   cloud-image in 12.04 has no 'python3'
   ideally 'curtin --install-deps install' would get the things it needs
