# Copyright (C) 2018 RedHat Inc.
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

"""add os_hidden column to images table"""

from alembic import op
from sqlalchemy import Boolean, Column, sql

# revision identifiers, used by Alembic.
revision = 'rocky_expand01'
down_revision = 'queens_expand01'
branch_labels = None
depends_on = None


def upgrade():
    h_col = Column('os_hidden', Boolean, default=False, nullable=False,
                   server_default=sql.expression.false())
    op.add_column('images', h_col)
    op.create_index('os_hidden_image_idx', 'images', ['os_hidden'])
