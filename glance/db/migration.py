# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2013 OpenStack Foundation
# Copyright 2013 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Database setup and migration commands."""

import os
import threading

from oslo_config import cfg
from oslo_db import options as db_options
from stevedore import driver


_IMPL = None
_LOCK = threading.Lock()

db_options.set_defaults(cfg.CONF)


def get_backend():
    global _IMPL
    if _IMPL is None:
        with _LOCK:
            if _IMPL is None:
                _IMPL = driver.DriverManager(
                    "glance.database.migration_backend",
                    cfg.CONF.database.backend).driver
    return _IMPL


# Migration-related constants
EXPAND_BRANCH = 'expand'
CONTRACT_BRANCH = 'contract'
CURRENT_RELEASE = 'victoria'
ALEMBIC_INIT_VERSION = 'liberty'
LATEST_REVISION = 'ussuri_contract01'
INIT_VERSION = 0

MIGRATE_REPO_PATH = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    'sqlalchemy',
    'migrate_repo',
)
