# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.util import get_platform_arch


class _ReleaseBase(object):
    repo = "maas-daily"
    arch = get_platform_arch()
    target_arch = arch
    mem = "2048"


class _UbuntuBase(_ReleaseBase):
    distro = "ubuntu"
    kflavor = "generic"
    target_distro = "ubuntu"


class _CentosFromUbuntuBase(_UbuntuBase):
    arch_skip = ['arm64', 'ppc64el']
    # base for installing centos tarballs from ubuntu base
    target_distro = "centos"
    target_ftype = "root-tgz"
    target_kflavor = None
    kflavor = "generic"


class _UbuntuCoreUbuntuBase(_UbuntuBase):
    # base for installing UbuntuCore root-image.xz from ubuntu base
    target_distro = "ubuntu-core"
    target_ftype = "root-image.xz"
    kflavor = None


class _Centos70FromXenialBase(_CentosFromUbuntuBase):
    # release for boot
    release = "xenial"
    # release for target
    target_release = "centos70"


class _Centos70FromBionicBase(_CentosFromUbuntuBase):
    # release for boot
    release = "bionic"
    # release for target
    target_release = "centos70"


class _Centos70FromFocalBase(_CentosFromUbuntuBase):
    # release for boot
    release = "focal"
    # release for target
    target_release = "centos70"


class _UbuntuCore16FromXenialBase(_UbuntuCoreUbuntuBase):
    # release for boot
    release = "xenial"
    # release for target
    target_release = "ubuntu-core-16"


class _UbuntuCore18FromBionicBase(_UbuntuCoreUbuntuBase):
    # release for boot
    release = "bionic"
    # release for target
    target_release = "ubuntu-core-18"


class _UbuntuCore20FromFocalBase(_UbuntuCoreUbuntuBase):
    # release for boot
    release = "focal"
    # release for target
    target_release = "ubuntu-core-20"


class _PreciseBase(_UbuntuBase):
    release = "xenial"
    target_release = "precise"
    target_distro = "ubuntu"
    target_ftype = "squashfs"


class _PreciseHWET(_PreciseBase):
    target_kernel_package = 'linux-generic-lts-trusty'


class _TrustyBase(_UbuntuBase):
    release = "trusty"
    target_release = "trusty"


class _TrustyHWEU(_TrustyBase):
    krel = "utopic"


class _TrustyHWEV(_TrustyBase):
    krel = "vivid"


class _TrustyHWEW(_TrustyBase):
    krel = "wily"


class _TrustyHWEX(_TrustyBase):
    krel = "xenial"


class _TrustyFromXenial(_TrustyBase):
    release = "xenial"
    target_release = "trusty"


class _XenialBase(_UbuntuBase):
    release = "xenial"
    target_release = "xenial"
    subarch = "ga-16.04"


class _XenialGA(_XenialBase):
    subarch = "ga-16.04"


class _XenialHWE(_XenialBase):
    subarch = "hwe-16.04"


class _XenialEdge(_XenialBase):
    subarch = "hwe-16.04-edge"


class _BionicBase(_UbuntuBase):
    release = "bionic"
    target_release = "bionic"
    if _UbuntuBase.arch == "arm64":
        subarch = "ga-18.04"


class _CosmicBase(_UbuntuBase):
    release = "cosmic"
    target_release = "cosmic"
    if _UbuntuBase.arch == "arm64":
        subarch = "ga-18.10"


class _DiscoBase(_UbuntuBase):
    release = "disco"
    target_release = "disco"
    # squashfs is over 300MB, need more ram
    if _UbuntuBase.arch == "arm64":
        subarch = "ga-19.04"


class _EoanBase(_UbuntuBase):
    release = "eoan"
    target_release = "eoan"
    if _UbuntuBase.arch == "arm64":
        subarch = "ga-19.10"


class _FocalBase(_UbuntuBase):
    release = "focal"
    target_release = "focal"
    if _UbuntuBase.arch == "arm64":
        subarch = "ga-20.04"


class _JammyBase(_UbuntuBase):
    release = "jammy"
    target_release = "jammy"
    if _UbuntuBase.arch == "arm64":
        subarch = "ga-22.04"


class _ManticBase(_UbuntuBase):
    release = "mantic"
    target_release = "mantic"
    if _UbuntuBase.arch == "arm64":
        subarch = "ga-23.10"


class _Releases(object):
    trusty = _TrustyBase
    precise = _PreciseBase
    precise_hwe_t = _PreciseHWET
    trusty_hwe_u = _TrustyHWEU
    trusty_hwe_v = _TrustyHWEV
    trusty_hwe_w = _TrustyHWEW
    trusty_hwe_x = _TrustyHWEX
    trustyfromxenial = _TrustyFromXenial
    xenial = _XenialBase
    xenial_ga = _XenialGA
    xenial_hwe = _XenialHWE
    xenial_edge = _XenialEdge
    bionic = _BionicBase
    cosmic = _CosmicBase
    disco = _DiscoBase
    eoan = _EoanBase
    focal = _FocalBase
    jammy = _JammyBase
    mantic = _ManticBase


class _CentosReleases(object):
    centos70_xenial = _Centos70FromXenialBase
    centos70_bionic = _Centos70FromBionicBase
    centos70_focal = _Centos70FromFocalBase


class _UbuntuCoreReleases(object):
    uc16fromxenial = _UbuntuCore16FromXenialBase
    uc18frombionic = _UbuntuCore18FromBionicBase
    uc20fromfocal = _UbuntuCore20FromFocalBase


base_vm_classes = _Releases
centos_base_vm_classes = _CentosReleases
ubuntu_core_base_vm_classes = _UbuntuCoreReleases

# vi: ts=4 expandtab syntax=python
