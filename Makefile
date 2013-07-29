TOP := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CWD := $(shell pwd)

check: pep8 pyflakes test

pep8:
	$(CWD)/tools/run-pep8

pyflakes:
	$(CWD)/tools/run-pyflakes

test:
	@nosetests3 $(noseopts) tests/


.PHONY: all test pyflakes pep8
