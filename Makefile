TOP := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CWD := $(shell pwd)
PYTHON ?= python3
COVERAGE ?= 1
DEFAULT_COVERAGEOPTS = --with-coverage --cover-erase --cover-branches --cover-package=curtin --cover-inclusive 
ifeq ($(COVERAGE), 1)
	coverageopts ?= $(DEFAULT_COVERAGEOPTS)
endif
CURTIN_VMTEST_IMAGE_SYNC ?= False
export CURTIN_VMTEST_IMAGE_SYNC
noseopts ?= -vv --nologcapture

build:

bin/curtin: curtin/pack.py tools/write-curtin
	$(PYTHON) tools/write-curtin bin/curtin

check: unittest

style-check: pep8 pyflakes pyflakes3

coverage: coverageopts ?= $(DEFAULT_COVERAGEOPTS)
coverage: unittest

pep8:
	@$(CWD)/tools/run-pep8

pyflakes:
	@$(CWD)/tools/run-pyflakes

pyflakes3:
	@$(CWD)/tools/run-pyflakes3

unittest:
	nosetests $(coverageopts) $(noseopts) tests/unittests
	nosetests3 $(coverageopts) $(noseopts) tests/unittests

docs:
	@which sphinx-build || \
		{ echo "Missing sphinx-build. Installing python3-sphinx..."; \
		  sleep 3; sudo apt-get install -qy python3-sphinx; }
	@[ -d /usr/lib/python3/dist-packages/sphinx_rtd_theme ] || \
		{ echo "Missing python3-sphinx-rtd-theme. Installing..."; \
		  sleep 3; sudo apt-get install -qy python3-sphinx-rtd-theme; }
	make -C doc html

# By default don't sync images when running all tests.
vmtest:
	nosetests3 $(noseopts) tests/vmtests

vmtest-deps:
	@$(CWD)/tools/vmtest-system-setup

sync-images:
	@$(CWD)/tools/vmtest-sync-images

clean:
	rm -rf doc/_build

.PHONY: all clean test pyflakes pyflakes3 pep8 build style-check
