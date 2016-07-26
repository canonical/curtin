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

check: pep8 pyflakes pyflakes3 unittest

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
		{ echo "need sphinx-build. get it:"; \
		  echo "   apt-get install -qy python3-sphinx"; exit 1; } 1>&2
	make -C doc html

# By default don't sync images when running all tests.
vmtest:
	nosetests3 $(noseopts) tests/vmtests

vmtest-deps:
	@$(CWD)/tools/vmtest-system-setup

sync-images:
	@$(CWD)/tools/vmtest-sync-images


.PHONY: all test pyflakes pyflakes3 pep8 build
