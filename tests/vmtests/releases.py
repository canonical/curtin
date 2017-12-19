from curtin.util import get_platform_arch


class _ReleaseBase(object):
    repo = "maas-daily"
    arch = get_platform_arch()


class _UbuntuBase(_ReleaseBase):
    distro = "ubuntu"
    kflavor = "generic"


class _CentosFromUbuntuBase(_UbuntuBase):
    # base for installing centos tarballs from ubuntu base
    target_distro = "centos"
    target_ftype = "vmtest.root-tgz"
    kflavor = None


class _UbuntuCoreUbuntuBase(_UbuntuBase):
    # base for installing UbuntuCore root-image.xz from ubuntu base
    target_distro = "ubuntu-core-16"
    target_ftype = "root-image.xz"
    kflavor = None


class _Centos70FromXenialBase(_CentosFromUbuntuBase):
    # release for boot
    release = "xenial"
    # release for target
    target_release = "centos70"


class _UbuntuCore16FromXenialBase(_UbuntuCoreUbuntuBase):
    # release for boot
    release = "xenial"
    # release for target
    target_release = "ubuntu-core-16"


class _Centos66FromXenialBase(_CentosFromUbuntuBase):
    release = "xenial"
    target_release = "centos66"


class _TrustyBase(_UbuntuBase):
    release = "trusty"


class _TrustyHWEU(_UbuntuBase):
    release = "trusty"
    krel = "utopic"


class _TrustyHWEV(_UbuntuBase):
    release = "trusty"
    krel = "vivid"


class _TrustyHWEW(_UbuntuBase):
    release = "trusty"
    krel = "wily"


class _TrustyHWEX(_UbuntuBase):
    release = "trusty"
    krel = "xenial"


class _TrustyFromXenial(_UbuntuBase):
    release = "xenial"
    target_release = "trusty"


class _XenialBase(_UbuntuBase):
    release = "xenial"
    subarch = "ga-16.04"


class _XenialGA(_UbuntuBase):
    release = "xenial"
    subarch = "ga-16.04"


class _XenialHWE(_UbuntuBase):
    release = "xenial"
    subarch = "hwe-16.04"


class _XenialEdge(_UbuntuBase):
    release = "xenial"
    subarch = "hwe-16.04-edge"


class _ZestyBase(_UbuntuBase):
    release = "zesty"


class _ArtfulBase(_UbuntuBase):
    release = "artful"


class _BionicBase(_UbuntuBase):
    release = "bionic"


class _Releases(object):
    trusty = _TrustyBase
    trusty_hwe_u = _TrustyHWEU
    trusty_hwe_v = _TrustyHWEV
    trusty_hwe_w = _TrustyHWEW
    trusty_hwe_x = _TrustyHWEX
    trustyfromxenial = _TrustyFromXenial
    xenial = _XenialBase
    xenial_ga = _XenialGA
    xenial_hwe = _XenialHWE
    xenial_edge = _XenialEdge
    zesty = _ZestyBase
    artful = _ArtfulBase
    bionic = _BionicBase


class _CentosReleases(object):
    centos70fromxenial = _Centos70FromXenialBase
    centos66fromxenial = _Centos66FromXenialBase


class _UbuntuCoreReleases(object):
    uc16fromxenial = _UbuntuCore16FromXenialBase


base_vm_classes = _Releases
centos_base_vm_classes = _CentosReleases
ubuntu_core_base_vm_classes = _UbuntuCoreReleases

# vi: ts=4 expandtab syntax=python
