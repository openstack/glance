#!/usr/bin/env bash
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

function configure_enforce_scope {
    iniset $GLANCE_CONF_DIR/glance-api.conf oslo_policy enforce_scope true
    iniset $GLANCE_CONF_DIR/glance-api.conf oslo_policy enforce_new_defaults true
    iniset $GLANCE_CONF_DIR/glance-api.conf DEFAULT enforce_secure_rbac true
    sudo systemctl restart devstack@g-api
}

function configure_protection_tests {
    iniset $TEMPEST_CONFIG image-feature-enabled enforce_scope true
    iniset $TEMPEST_CONFIG auth admin_system true
    iniset $TEMPEST_CONFIG auth admin_project_name ''
}

# For more information on Devstack plugins, including a more detailed
# explanation on when the different steps are executed please see:
# https://docs.openstack.org/devstack/latest/plugins.html

if [[ "$1" == "stack" && "$2" == "test-config" ]]; then
    # This phase is executed after Tempest was configured
    echo "Glance plugin - Test-config phase"
    if [[ "$(trueorfalse False GLANCE_ENFORCE_SCOPE)" == "True" ]] ; then
        # devstack and tempest assume enforce_scope is false, so need to wait
        # until the final phase to turn it on
        configure_enforce_scope
        configure_protection_tests
    fi
fi
