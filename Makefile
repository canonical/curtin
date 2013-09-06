TOP := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CWD := $(shell pwd)

build:

check: pep8 pyflakes test

pep8:
	@$(CWD)/tools/run-pep8

pyflakes:
	@$(CWD)/tools/run-pyflakes

test:
	nosetests $(noseopts) tests/
	nosetests3 $(noseopts) tests


.PHONY: all test pyflakes pep8 build
