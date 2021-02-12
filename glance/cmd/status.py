#!/usr/bin/env python

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

import sys

import glance_store
from oslo_config import cfg
from oslo_upgradecheck import common_checks
from oslo_upgradecheck import upgradecheck

from glance.common import removed_config
from glance.common import wsgi  # noqa

CONF = cfg.CONF

SUCCESS = upgradecheck.Code.SUCCESS
FAILURE = upgradecheck.Code.FAILURE


class Checks(upgradecheck.UpgradeCommands):
    """Programmable upgrade checks."""

    def __init__(self, *args, **kwargs):
        super(upgradecheck.UpgradeCommands).__init__(*args, **kwargs)
        removed_config.register_removed_options()

    def _check_sheepdog_store(self):
        """Check that the removed sheepdog backend store is not configured."""
        glance_store.register_opts(CONF)
        sheepdog_present = False
        if 'sheepdog' in (getattr(CONF, 'enabled_backends') or {}):
            sheepdog_present = True

        if 'sheepdog' in (getattr(CONF.glance_store, 'stores') or []):
            sheepdog_present = True

        if sheepdog_present:
            return upgradecheck.Result(
                FAILURE,
                'The "sheepdog" backend store driver has been removed, but '
                'current settings have it configured.')

        return upgradecheck.Result(SUCCESS)

    def _check_owner_is_tenant(self):
        if CONF.owner_is_tenant is False:
            return upgradecheck.Result(
                FAILURE,
                'The "owner_is_tenant" option has been removed and there is '
                'no upgrade path for installations that had this option set '
                'to False.')
        return upgradecheck.Result(SUCCESS)

    _upgrade_checks = (
        # Added in Ussuri
        ('Sheepdog Driver Removal', _check_sheepdog_store),
        # Added in Wallaby
        ('Policy File JSON to YAML Migration',
         (common_checks.check_policy_json, {'conf': CONF})),
        # Removed in Wallaby
        ('Config option owner_is_tenant removal', _check_owner_is_tenant),
    )


def main():
    try:
        return upgradecheck.main(CONF, 'glance', Checks())
    except cfg.ConfigDirNotFoundError:
        return ('ERROR: cannot read the glance configuration directory.\n'
                'Please re-run using the --config-dir <dirname> option '
                'with a valid glance configuration directory.')


if __name__ == '__main__':
    sys.exit(main())
