VERSION = '0.1.0'

from distutils.core import setup
from glob import glob
import os


def is_f(p):
    return os.path.isfile(p)

setup(
    name="curtin",
    description='The curtin installer',
    version=VERSION,
    author='Scott Moser',
    author_email='scott.moser@canonical.com',
    license="AGPL",
    url='http://launchpad.net/curtin/',
    packages=[
        'curtin',
        'curtin.block',
        'curtin.deps',
        'curtin.commands',
        'curtin.net',
        'curtin.reporter'
    ],
    scripts=glob('bin/*'),
    data_files=[
        ('/usr/share/doc/curtin',
         [f for f in glob('doc/*') if is_f(f)]),
        ('/usr/lib/curtin/helpers',
         [f for f in glob('helpers/*') if is_f(f)])
    ]
)
