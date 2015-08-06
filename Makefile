TOP := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CWD := $(shell pwd)
PYTHON ?= python3

build:

bin/curtin: curtin/pack.py tools/write-curtin
	$(PYTHON) tools/write-curtin bin/curtin

check: pep8 pyflakes pyflakes3 unittest

pep8:
	@$(CWD)/tools/run-pep8

pyflakes:
	@$(CWD)/tools/run-pyflakes

pyflakes3:
	@$(CWD)/tools/run-pyflakes

unittest:
	nosetests $(noseopts) tests/unittests
	nosetests3 $(noseopts) tests/unittests

vmtest:
	nosetests3 $(noseopts) tests/vmtests


.PHONY: all test pyflakes pyflakes3 pep8 build
