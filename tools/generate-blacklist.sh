#!/bin/bash -xe

TOX_INI_DIR="$1"
TOX_TMP_DIR="$2"

cat "${TOX_INI_DIR}/serial-functests.txt" \
    "${TOX_INI_DIR}/broken-functional-py35-ssl-tests.txt" > \
    "${TOX_TMP_DIR}/func-py35-blacklist.txt"

