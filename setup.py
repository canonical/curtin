from glob import glob
import os
import sys

import setuptools

import curtin


def is_f(p):
    return os.path.isfile(p)


def in_virtualenv():
    try:
        if sys.real_prefix == sys.prefix:
            return False
        else:
            return True
    except AttributeError:
        return False


USR = "usr" if in_virtualenv() else "/usr"

setuptools.setup(
    name="curtin",
    description='The curtin installer',
    version=curtin.__version__,
    author='Scott Moser',
    author_email='scott.moser@canonical.com',
    license="AGPL",
    url='http://launchpad.net/curtin/',
    packages=setuptools.find_packages('.', include=['curtin', 'curtin.*']),
    scripts=glob('bin/*'),
    data_files=[
        (USR + '/share/doc/curtin',
         [f for f in glob('doc/*') if is_f(f)]),
        (USR + '/lib/curtin/helpers',
         [f for f in glob('helpers/*') if is_f(f)])
    ]
)
