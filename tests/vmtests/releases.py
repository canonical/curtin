class _ReleaseBase(object):
    repo = "maas-daily"
    arch = "amd64"


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
    # FIXME: net.ifnames=0 should not be required as image should
    #        eventually address this internally.  Note, also we do
    #        currently need this copied over to the installed environment
    #        although in theory the udev rules we write should fix that.
    extra_kern_args = "--- net.ifnames=0"


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

base_vm_classes = _Releases

# vi: ts=4 expandtab syntax=python
