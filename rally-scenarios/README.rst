This directory contains rally benchmark scenarios to be run by OpenStack CI.

Structure:
* glance.yaml is rally task that will be run in gates
* plugins - directory where you can add rally plugins. So you don't need
  to merge benchmark in scenarios in rally to be able to run them in glance.
* extra - all files from this directory will be copy pasted to gets, so you
  are able to use absolute path in rally tasks. Files will be in ~/.rally/extra/*


* more about rally: https://wiki.openstack.org/wiki/Rally
* how to add rally-gates: https://wiki.openstack.org/wiki/Rally/RallyGates
* how to write plugins https://rally.readthedocs.org/en/latest/plugins.html
