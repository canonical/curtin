TOP := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CWD := $(shell pwd)
PYTHON3 ?= python3
COVERAGE ?= 1
DEFAULT_COVERAGEOPTS = --with-coverage --cover-erase --cover-branches --cover-package=curtin --cover-inclusive 
ifeq ($(COVERAGE), 1)
	coverageopts ?= $(DEFAULT_COVERAGEOPTS)
endif
CURTIN_VMTEST_IMAGE_SYNC ?= False
export CURTIN_VMTEST_IMAGE_SYNC
noseopts ?= -vv
pylintopts ?= --rcfile=pylintrc --errors-only
target_dirs ?= curtin tests tools

build:

bin/curtin: curtin/pack.py tools/write-curtin
	$(PYTHON3) tools/write-curtin bin/curtin

check: unittest

style-check: pep8 pyflakes3

coverage: coverageopts ?= $(DEFAULT_COVERAGEOPTS)
coverage: unittest

pep8:
	@$(CWD)/tools/run-pep8

pyflakes pyflakes3:
	$(PYTHON3) -m pyflakes $(target_dirs)

pylint pylint3:
	$(PYTHON3) -m pylint $(pylintopts) $(target_dirs)

unittest unittest3:
	$(PYTHON3) -m nose $(coverageopts) $(noseopts) tests/unittests

schema-validate:
	@$(CWD)/tools/schema-validate-storage

docs: check-doc-deps
	make -C doc html

check-doc-deps:
	@which sphinx-build && $(PYTHON3) -c 'import sphinx_rtd_theme' || \
		{ echo "Missing doc dependencies. Install with:"; \
		  pkgs="python3-sphinx-rtd-theme python3-sphinx"; \
		  echo sudo apt-get install -qy $$pkgs ; exit 1; }

# By default don't sync images when running all tests.
vmtest: schema-validate
	$(PYTHON3) -m nose $(noseopts) tests/vmtests

vmtest-deps:
	@$(CWD)/tools/vmtest-system-setup

sync-images:
	@$(CWD)/tools/vmtest-sync-images

integration-deps:
	@$(CWD)/tools/vmtest-create-static-images

integration: integration-deps
	$(PYTHON3) -m pytest tests/integration

clean:
	rm -rf doc/_build

.PHONY: all clean test pyflakes pyflakes3 pep8 build style-check check-doc-deps
