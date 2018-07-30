# Copyright (C) 2018 Verizon Wireless
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

"""add os_hash_algo and os_hash_value columns to images table"""

from alembic import op
from sqlalchemy import Column, String

# revision identifiers, used by Alembic.
revision = 'rocky_expand02'
down_revision = 'rocky_expand01'
branch_labels = None
depends_on = None


def upgrade():
    algo_col = Column('os_hash_algo', String(length=64), nullable=True)
    value_col = Column('os_hash_value', String(length=128), nullable=True)
    op.add_column('images', algo_col)
    op.add_column('images', value_col)
    op.create_index('os_hash_value_image_idx', 'images', ['os_hash_value'])
