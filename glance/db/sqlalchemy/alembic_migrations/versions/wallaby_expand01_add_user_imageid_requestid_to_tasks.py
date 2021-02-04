# Copyright (C) 2021 RedHat Inc
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

"""add image_id, request_id, user columns to tasks table"

Revision ID: wallaby_expand01
Revises: ussuri_expand01
Create Date: 2021-02-04 11:55:16.657499

"""

from alembic import op
from sqlalchemy import String, Column

# revision identifiers, used by Alembic.
revision = 'wallaby_expand01'
down_revision = 'ussuri_expand01'
branch_labels = None
depends_on = None


def upgrade():
    image_id_col = Column('image_id', String(length=36), nullable=True)
    request_id_col = Column('request_id', String(length=64), nullable=True)
    user_col = Column('user_id', String(length=64), nullable=True)
    op.add_column('tasks', image_id_col)
    op.add_column('tasks', request_id_col)
    op.add_column('tasks', user_col)
    op.create_index('ix_tasks_image_id', 'tasks', ['image_id'])
