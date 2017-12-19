class _ReleaseBase(object):
    repo = "maas-daily"
    arch = "amd64"


class _PreciseBase(_ReleaseBase):
    release = "precise"


class _TrustyBase(_ReleaseBase):
    release = "trusty"


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
    trusty = _TrustyBase
    vivid = _VividBase
    wily = _WilyBase
    xenial = _XenialBase

base_vm_classes = _Releases

# vi: ts=4 expandtab syntax=python
