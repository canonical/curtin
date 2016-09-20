from curtin.util import get_platform_arch


class _ReleaseBase(object):
    repo = "maas-daily"
    arch = get_platform_arch()


class _UbuntuBase(_ReleaseBase):
    distro = "ubuntu"


class _PreciseBase(_UbuntuBase):
    release = "precise"


class _PreciseHWET(_UbuntuBase):
    release = "precise"
    krel = "trusty"


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


class _VividBase(_UbuntuBase):
    release = "vivid"


class _WilyBase(_UbuntuBase):
    release = "wily"


class _XenialBase(_UbuntuBase):
    release = "xenial"


class _YakketyBase(_UbuntuBase):
    release = "yakkety"


class _Releases(object):
    precise = _PreciseBase
    precise_hwe_t = _PreciseHWET
    trusty = _TrustyBase
    trusty_hwe_u = _TrustyHWEU
    trusty_hwe_v = _TrustyHWEV
    trusty_hwe_w = _TrustyHWEW
    vivid = _VividBase
    wily = _WilyBase
    xenial = _XenialBase
    yakkety = _YakketyBase

base_vm_classes = _Releases

# vi: ts=4 expandtab syntax=python
