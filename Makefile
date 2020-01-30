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

unittest2:
	nosetests $(coverageopts) $(noseopts) tests/unittests

unittest3:
	nosetests3 $(coverageopts) $(noseopts) tests/unittests

unittest: unittest2 unittest3

schema-validate:
	@$(CWD)/tools/schema-validate-storage

docs: check-doc-deps
	make -C doc html

check-doc-deps:
	@which sphinx-build && $(PYTHON) -c 'import sphinx_rtd_theme' || \
		{ echo "Missing doc dependencies. Install with:"; \
		  pkgs="python3-sphinx-rtd-theme python3-sphinx"; \
		  echo sudo apt-get install -qy $$pkgs ; exit 1; }

# By default don't sync images when running all tests.
vmtest: schema-validate
	nosetests3 $(noseopts) tests/vmtests

vmtest-deps:
	@$(CWD)/tools/vmtest-system-setup

sync-images:
	@$(CWD)/tools/vmtest-sync-images

clean:
	rm -rf doc/_build

.PHONY: all clean test pyflakes pyflakes3 pep8 build style-check check-doc-deps
