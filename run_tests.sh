#!/bin/bash

function usage {
  echo "Usage: $0 [OPTION]..."
  echo "Run Glance's test suite(s)"
  echo ""
  echo "  -V, --virtual-env        Always use virtualenv.  Install automatically if not present"
  echo "  -N, --no-virtual-env     Don't use virtualenv.  Run tests in local environment"
  echo "  -h, --help               Print this usage message"
  echo ""
  echo "Note: with no options specified, the script will try to run the tests in a virtual environment,"
  echo "      If no virtualenv is found, the script will ask if you would like to create one.  If you "
  echo "      prefer to run tests NOT in a virtual environment, simply pass the -N option."
  exit
}

function process_options {
  array=$1
  elements=${#array[@]}
  for (( x=0;x<$elements;x++)); do
    process_option ${array[${x}]}
  done
}

function process_option {
  option=$1
  case $option in
    -h|--help) usage;;
    -V|--virtual-env) let always_venv=1; let never_venv=0;;
    -N|--no-virtual-env) let always_venv=0; let never_venv=1;;
  esac
}

venv=.glance-venv
with_venv=tools/with_venv.sh
always_venv=0
never_venv=0
options=("$@")

process_options $options

if [ $never_venv -eq 1 ]; then
  # Just run the test suites in current environment
  nosetests --logging-clear-handlers
  exit
fi

if [ -e ${venv} ]; then
  ${with_venv} nosetests --logging-clear-handlers
else  
  if [ $always_venv -eq 1 ]; then
    # Automatically install the virtualenv
    python tools/install_venv.py
  else
    echo -e "No virtual environment found...create one? (Y/n) \c"
    read use_ve
    if [ "x$use_ve" = "xY" ]; then
      # Install the virtualenv and run the test suite in it
      python tools/install_venv.py
    else
      nosetests --logging-clear-handlers
      exit
    fi
  fi
  ${with_venv} nosetests --logging-clear-handlers
fi
