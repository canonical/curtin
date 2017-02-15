#!/bin/bash -x

# 
# Acquire snappy image
# wget http://cdimage.ubuntu.com/ubuntu-core/16/stable/ubuntu-core-16-amd64.img.xz
#  

# make sync-images
# 
DATE=20170209
ROOT=/srv/images/xenial/amd64/${DATE}/vmtest.root-image 
KERNEL=/srv/images/xenial/amd64/${DATE}/xenial/generic/boot-kernel 
INITRD=/srv/images/xenial/amd64/${DATE}/xenial/generic/boot-initrd 
PUBLISH=`pwd`/ubuntu-core-16-amd64.img.xz
DISK="snappy.img"

# the ::dd-tgz tells curtin that it doesn't have to extract a root tarball
./tools/launch $ROOT \
  --kernel $KERNEL \
  --initrd $INITRD \
  --publish ${PUBLISH}::dd-tgz \
  --disk ${DISK} \
  -n user \
  -vv \
  --serial telnet:localhost:2447,nowait,server \
  --silent \
  --power=off \
   curtin install PUBURL/`basename $PUBLISH`
