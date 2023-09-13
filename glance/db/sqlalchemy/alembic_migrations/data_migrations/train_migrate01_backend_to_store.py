# Copyright 2019 RedHat Inc
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

from sqlalchemy import sql


def has_migrations(engine):
    """Returns true if at least one data row can be migrated.

    There are rows left to migrate if meta_data column has
    {"backend": "...."}

    Note: This method can return a false positive if data migrations
    are running in the background as it's being called.
    """
    sql_query = sql.text(
        "select meta_data from image_locations where "
        "INSTR(meta_data, '\"backend\":') > 0"
    )

    # NOTE(abhishekk): INSTR function doesn't supported in postgresql
    if engine.name == 'postgresql':
        sql_query = sql.text(
            "select meta_data from image_locations where "
            "POSITION('\"backend\":' IN meta_data) > 0"
        )

    with engine.connect() as conn, conn.begin():
        metadata_backend = conn.execute(sql_query)
        if metadata_backend.rowcount > 0:
            return True

    return False


def migrate(engine):
    """Replace 'backend' with 'store' in meta_data column of image_locations"""
    sql_query = sql.text(
        "UPDATE image_locations SET meta_data = REPLACE(meta_data, "
        "'\"backend\":', '\"store\":') where INSTR(meta_data, "
        " '\"backend\":') > 0"
    )

    # NOTE(abhishekk): INSTR function doesn't supported in postgresql
    if engine.name == 'postgresql':
        sql_query = sql.text(
            "UPDATE image_locations SET meta_data = REPLACE("
            "meta_data, '\"backend\":', '\"store\":') where "
            "POSITION('\"backend\":' IN meta_data) > 0"
        )

    with engine.connect() as conn, conn.begin():
        migrated_rows = conn.execute(sql_query)
        return migrated_rows.rowcount
