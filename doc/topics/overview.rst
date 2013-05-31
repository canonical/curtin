========
Overview
========

Curtin is intended to be a bare bones "installer".   Its goal is to take data from a source, and get it onto disk as quick as possible and then boot it.  The key difference from traditional package based installers is that curtin assumes the thing its installing is intelligent and will do the right thing.

Stages
------
A usage of curtin will go through the following stages:

- install environment boot
- early commands
- partitioning
- installation of sources to disk
- hook for installed OS to customize itself
- final commands
