# Copyright 2016 Rackspace
# Copyright 2013 Intel Corporation
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

import os

from alembic import config as alembic_config
from alembic import migration as alembic_migration
from alembic import script as alembic_script
from sqlalchemy import MetaData, Table

from glance.db.sqlalchemy import api as db_api


def get_alembic_config(engine=None):
    """Return a valid alembic config object"""
    ini_path = os.path.join(os.path.dirname(__file__), 'alembic.ini')
    config = alembic_config.Config(os.path.abspath(ini_path))
    # we don't want to use the logger configuration from the file, which is
    # only really intended for the CLI
    # https://stackoverflow.com/a/42691781/613428
    config.attributes['configure_logger'] = False
    if engine is None:
        engine = db_api.get_engine()
    # str(sqlalchemy.engine.url.URL) returns a RFC-1738 quoted URL.
    # This means that a password like "foo@" will be turned into
    # "foo%40".  This causes a problem for set_main_option() here
    # because that uses ConfigParser.set, which (by design) uses
    # *python* interpolation to write the string out ... where "%" is
    # the special python interpolation character!  Avoid this
    # mismatch by quoting all %'s for the set below.
    quoted_engine_url = str(engine.url).replace('%', '%%')
    config.set_main_option('sqlalchemy.url', quoted_engine_url)
    return config


def get_current_alembic_heads():
    """Return current heads (if any) from the alembic migration table"""
    engine = db_api.get_engine()
    with engine.connect() as conn:
        context = alembic_migration.MigrationContext.configure(conn)
        heads = context.get_current_heads()

        def update_alembic_version(old, new):
            """Correct alembic head in order to upgrade DB using EMC method.

            :param:old: Actual alembic head
            :param:new: Expected alembic head to be updated
            """
            meta = MetaData()
            alembic_version = Table(
                'alembic_version', meta, autoload_with=engine)
            alembic_version.update().values(
                version_num=new).where(
                alembic_version.c.version_num == old).execute()

        if "pike01" in heads:
            update_alembic_version("pike01", "pike_contract01")
        elif "ocata01" in heads:
            update_alembic_version("ocata01", "ocata_contract01")

        heads = context.get_current_heads()
        return heads


def get_alembic_branch_head(branch):
    """Return head revision name for particular branch"""
    a_config = get_alembic_config()
    script = alembic_script.ScriptDirectory.from_config(a_config)
    return script.revision_map.get_current_head(branch)
