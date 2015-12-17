class _AttrDict(dict):
    # http://stackoverflow.com/questions/4984647/
    #     accessing-dict-keys-like-an-attribute-in-python
    def __init__(self, *args, **kwargs):
        super(_AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


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


base_vm_classes = _AttrDict({
   'precise': _PreciseBase,
   'trusty': _TrustyBase,
   'vivid': _VividBase,
   'wily': _WilyBase,
   'xenial': _XenialBase,
})

# vi: ts=4 expandtab syntax=python
