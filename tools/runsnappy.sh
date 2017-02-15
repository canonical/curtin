#!/bin/bash -x

# After running this script, In another window:
#   telnet localhost 2447 
# 
#   And after configure snappy, you can
#   ssh -p 22222 <snappy user>@localhost
#

BOOT=snappy.img
SEED=seed.img

[ ! -e ${SEED} ] && {
    [ ! -e user-data ] && {
        echo "You need a 'user-data' file"
        exit 1;
    }
    echo "instance-id: $(uuidgen || echo i-abcdefg)" > meta-data
   echo "Creating seed..."
    cloud-localds ${SEED} user-data meta-data
}

qemu-system-x86_64 -enable-kvm -m 1024 \
    -snapshot \
    -drive file=${BOOT},format=raw,if=virtio \
    -cdrom $SEED \
    -net user -net nic,model=virtio \
    -redir tcp:22222:22 \
    -monitor stdio \
    -serial telnet:localhost:2447,nowait,server \
    -nographic
