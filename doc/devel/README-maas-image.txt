A maas image is also convenient for curtin development.

Using a maas image requires you to be able to be root to convert the
root-image.gz file into a -root.tar.gz file that is installable by curtin.
But other than that, the maas image is very convenient.

follow doc/devel/README.txt, but instead of the 'get cloud image' section
 do the following.

## this gets root image url that you could find from traversing
##  http://maas.ubuntu.com/images/ephemeral-v2/daily/xenial/amd64/
rel=xenial
streams_url="http://maas.ubuntu.com/images/ephemeral-v2/daily/streams/v1/index.json"
root_img_url=$(sstream-query \
   --output-format="%(item_url)s" --max=1 \
   ${streams_url} release=$rel ftype=root-image.gz arch=amd64 krel=$rel)

root_img_gz="${root_img_url##*/}"
root_img=${root_img_gz%.gz}

## download the root_img_url to local .gz file
[ -f "$root_img" ] ||
  { wget "${root_img_url}" -O "${root_img_gz}.tmp" && mv "${root_img_gz}.tmp" "$root_img_gz" ; }

## maas2roottar to 
##  a.) create the root_img file [root-image]
##  b.) extract kernel and initramfs root-image-kernel, root-image-initramfs]
##  c.) convert maas image to installable tarball [root-image.tar.gz]
## and pull the kernel and initramfs out
[ -f "$root_img" ] || ./tools/maas2roottar -vv --krd "${root_img_gz}"


## launch it using --kernel, --initrd
./tools/launch \
   ./root-image --kernel=./root-image-kernel --initrd=./root-image-initrd \
   -v --publish ./root-image.tar.gz -- \
   curtin -vv install "PUBURL/root-image.tar.gz"
