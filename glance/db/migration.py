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

from glance.common import utils
from glance.db.sqlalchemy import api as db_api

IMPL = utils.LazyPluggable(
    'backend',
    config_group='database',
    sqlalchemy='glance.openstack.common.db.sqlalchemy.migration')

INIT_VERSION = 0

MIGRATE_REPO_PATH = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    'sqlalchemy',
    'migrate_repo',
)


def db_sync(version=None, init_version=0):
    """Migrate the database to `version` or the most recent version."""
    return IMPL.db_sync(engine=db_api.get_engine(),
                        abs_path=MIGRATE_REPO_PATH,
                        version=version,
                        init_version=init_version)
