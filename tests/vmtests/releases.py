from curtin.util import get_platform_arch


class _ReleaseBase(object):
    repo = "maas-daily"
    arch = get_platform_arch()


class _PreciseBase(_ReleaseBase):
    release = "precise"


class _PreciseHWET(_ReleaseBase):
    release = "precise"
    krel = "trusty"


class _TrustyBase(_ReleaseBase):
    release = "trusty"


class _TrustyHWEU(_ReleaseBase):
    release = "trusty"
    krel = "utopic"


class _TrustyHWEV(_ReleaseBase):
    release = "trusty"
    krel = "vivid"


class _TrustyHWEW(_ReleaseBase):
    release = "trusty"
    krel = "wily"


class _VividBase(_ReleaseBase):
    release = "vivid"


class _WilyBase(_ReleaseBase):
    release = "wily"


class _XenialBase(_ReleaseBase):
    release = "xenial"


class _YakketyBase(_ReleaseBase):
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
