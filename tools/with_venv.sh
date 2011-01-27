#!/bin/bash
TOOLS=`dirname $0`
VENV=$TOOLS/../.glance-venv
source $VENV/bin/activate && $@
