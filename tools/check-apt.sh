#!/bin/bash
set -ue

# check no-conf exit paths for expected result
noconfexp="No apt config provided, skipping"
noconf1=$(echo "{}" | ./bin/curtin -v --config - apt --target /tmp 2>&1)
noconf2=$(./bin/curtin -v apt --target /tmp 2>&1)
if [ "${noconf1}" != "${noconfexp}" ]; then
    echo "Error: ${noconf1} != ${noconfexp}"
    exit 1
fi
if [ "${noconf2}" != "${noconfexp}" ]; then
    echo "Error: ${noconf2} != ${noconfexp}"
    exit 1
fi

# check for expected error trying to get to a non existing dir
./bin/curtin --verbose --config examples/tests/apt_source_cmd.yaml apt --target /doesnotexistcheckme 2>&1 | grep "^PermissionError" | grep doesnotexistcheckme -q

# check for valid config in expected error
conffail=$(./bin/curtin --verbose --config examples/tests/apt_source_cmd.yaml apt --target /tmp 2>&1 | grep "Failed to configure apt features")
# the order can change, so just grep for some known content to get some coverage
echo ${conffail} | grep -q "'preserve_sources_list': True"
echo ${conffail} | grep -q "'uri': 'http://us.archive.ubuntu.com/ubuntu'"
echo ${conffail} | grep -q "'uri': 'http://security.ubuntu.com/ubuntu'"
