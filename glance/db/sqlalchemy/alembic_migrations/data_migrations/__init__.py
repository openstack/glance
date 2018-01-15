# Copyright 2016 Rackspace
# Copyright 2016 Intel Corporation
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

import importlib
import os.path
import pkgutil

from glance.common import exception
from glance.db import migration as db_migrations
from glance.db.sqlalchemy import api as db_api


def _find_migration_modules(release):
    migrations = list()
    for _, module_name, _ in pkgutil.iter_modules([os.path.dirname(__file__)]):
        if module_name.startswith(release):
            migrations.append(module_name)

    migration_modules = list()
    for migration in sorted(migrations):
        module = importlib.import_module('.'.join([__package__, migration]))
        has_migrations_function = getattr(module, 'has_migrations', None)
        migrate_function = getattr(module, 'migrate', None)

        if has_migrations_function is None or migrate_function is None:
            raise exception.InvalidDataMigrationScript(script=module.__name__)

        migration_modules.append(module)

    return migration_modules


def _run_migrations(engine, migrations):
    rows_migrated = 0
    for migration in migrations:
        if migration.has_migrations(engine):
            rows_migrated += migration.migrate(engine)

    return rows_migrated


def has_pending_migrations(engine=None, release=db_migrations.CURRENT_RELEASE):
    if not engine:
        engine = db_api.get_engine()

    migrations = _find_migration_modules(release)
    if not migrations:
        return False
    return any([x.has_migrations(engine) for x in migrations])


def migrate(engine=None, release=db_migrations.CURRENT_RELEASE):
    if not engine:
        engine = db_api.get_engine()

    migrations = _find_migration_modules(release)
    rows_migrated = _run_migrations(engine, migrations)
    return rows_migrated
