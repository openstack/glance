# Copyright 2013 Rackspace
# All Rights Reserved.
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

from sqlalchemy.schema import (Column, ForeignKey, MetaData, Table)

from glance.db.sqlalchemy.migrate_repo.schema import (String,
                                                      Text,
                                                      create_tables,
                                                      drop_tables)  # noqa

TASKS_MIGRATE_COLUMNS = ['input', 'message', 'result']


def define_task_info_table(meta):
    Table('tasks', meta, autoload=True)
    # NOTE(nikhil): input and result are stored as text in the DB.
    # SQLAlchemy marshals the data to/from JSON using custom type
    # JSONEncodedDict. It uses simplejson underneath.
    task_info = Table('task_info',
                      meta,
                      Column('task_id', String(36),
                             ForeignKey('tasks.id'),
                             primary_key=True,
                             nullable=False),
                      Column('input', Text()),
                      Column('result', Text()),
                      Column('message', Text()),
                      mysql_engine='InnoDB',
                      mysql_charset='utf8')

    return task_info


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    tables = [define_task_info_table(meta)]
    create_tables(tables)

    tasks_table = Table('tasks', meta, autoload=True)
    task_info_table = Table('task_info', meta, autoload=True)

    tasks = tasks_table.select().execute().fetchall()
    for task in tasks:
        values = {
            'task_id': task.id,
            'input': task.input,
            'result': task.result,
            'message': task.message,
        }
        task_info_table.insert(values=values).execute()

    for col_name in TASKS_MIGRATE_COLUMNS:
        tasks_table.columns[col_name].drop()


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    tasks_table = Table('tasks', meta, autoload=True)
    task_info_table = Table('task_info', meta, autoload=True)

    for col_name in TASKS_MIGRATE_COLUMNS:
        column = Column(col_name, Text())
        column.create(tasks_table)

    task_info_records = task_info_table.select().execute().fetchall()

    for task_info in task_info_records:
        values = {
            'input': task_info.input,
            'result': task_info.result,
            'message': task_info.message
        }

        tasks_table.update(values=values).where(
            tasks_table.c.id == task_info.task_id).execute()

    drop_tables([task_info_table])
