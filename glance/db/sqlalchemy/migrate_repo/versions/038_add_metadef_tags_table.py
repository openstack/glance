# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

from sqlalchemy.schema import (
    Column, Index, MetaData, Table, UniqueConstraint)  # noqa

from glance.db.sqlalchemy.migrate_repo.schema import (
    DateTime, Integer, String, create_tables, drop_tables)  # noqa


def define_metadef_tags_table(meta):
    _constr_kwargs = {}
    metadef_tags = Table('metadef_tags',
                         meta,
                         Column('id', Integer(), primary_key=True,
                                nullable=False),
                         Column('namespace_id', Integer(),
                                nullable=False),
                         Column('name', String(80), nullable=False),
                         Column('created_at', DateTime(), nullable=False),
                         Column('updated_at', DateTime()),
                         UniqueConstraint('namespace_id', 'name',
                                          **_constr_kwargs),
                         mysql_engine='InnoDB',
                         mysql_charset='utf8',
                         extend_existing=False)

    if meta.bind.name != 'ibm_db_sa':
        Index('ix_tags_namespace_id_name',
              metadef_tags.c.namespace_id,
              metadef_tags.c.name)

    return metadef_tags


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_metadef_tags_table(meta)]
    create_tables(tables)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_metadef_tags_table(meta)]
    drop_tables(tables)
