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

from alembic import op
from sqlalchemy.schema import (
    Column, PrimaryKeyConstraint, ForeignKeyConstraint)

from glance.db.sqlalchemy.schema import (
    Boolean, DateTime, String, Text)  # noqa
from glance.db.sqlalchemy.models import JSONEncodedDict


def _add_tasks_table():
    op.create_table('tasks',
                    Column('id', String(length=36), nullable=False),
                    Column('type', String(length=30), nullable=False),
                    Column('status', String(length=30), nullable=False),
                    Column('owner', String(length=255), nullable=False),
                    Column('expires_at', DateTime(), nullable=True),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime(), nullable=True),
                    Column('deleted_at', DateTime(), nullable=True),
                    Column('deleted', Boolean(), nullable=False),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_tasks_deleted', 'tasks', ['deleted'], unique=False)
    op.create_index('ix_tasks_owner', 'tasks', ['owner'], unique=False)
    op.create_index('ix_tasks_status', 'tasks', ['status'], unique=False)
    op.create_index('ix_tasks_type', 'tasks', ['type'], unique=False)
    op.create_index('ix_tasks_updated_at',
                    'tasks',
                    ['updated_at'],
                    unique=False)


def _add_task_info_table():
    op.create_table('task_info',
                    Column('task_id', String(length=36), nullable=False),
                    Column('input', JSONEncodedDict(), nullable=True),
                    Column('result', JSONEncodedDict(), nullable=True),
                    Column('message', Text(), nullable=True),
                    ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
                    PrimaryKeyConstraint('task_id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)


def upgrade():
    _add_tasks_table()
    _add_task_info_table()
