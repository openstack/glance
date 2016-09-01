# Copyright 2013 OpenStack Foundation
# All Rights Reserved.
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

from sqlalchemy.schema import (Column, MetaData, Table, Index)

from glance.db.sqlalchemy.migrate_repo.schema import (
    Boolean, DateTime, String, Text, create_tables)  # noqa


def define_tasks_table(meta):
    tasks = Table('tasks',
                  meta,
                  Column('id', String(36), primary_key=True, nullable=False),
                  Column('type', String(30), nullable=False),
                  Column('status', String(30), nullable=False),
                  Column('owner', String(255), nullable=False),
                  Column('input', Text()),  # json blob
                  Column('result', Text()),  # json blob
                  Column('message', Text()),
                  Column('expires_at', DateTime(), nullable=True),
                  Column('created_at', DateTime(), nullable=False),
                  Column('updated_at', DateTime()),
                  Column('deleted_at', DateTime()),
                  Column('deleted',
                         Boolean(),
                         nullable=False,
                         default=False),
                  mysql_engine='InnoDB',
                  mysql_charset='utf8',
                  extend_existing=True)

    Index('ix_tasks_type', tasks.c.type)
    Index('ix_tasks_status', tasks.c.status)
    Index('ix_tasks_owner', tasks.c.owner)
    Index('ix_tasks_deleted', tasks.c.deleted)
    Index('ix_tasks_updated_at', tasks.c.updated_at)

    return tasks


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_tasks_table(meta)]
    create_tables(tables)
