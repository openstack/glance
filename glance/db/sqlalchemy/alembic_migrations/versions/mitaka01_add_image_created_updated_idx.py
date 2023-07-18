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

"""add index on created_at and updated_at columns of 'images' table

Revision ID: mitaka01
Revises: liberty
Create Date: 2016-08-03 17:19:35.306161

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'mitaka01'
down_revision = 'liberty'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('images') as batch_op:
        batch_op.create_index(
            'created_at_image_idx',
            ['created_at'],
        )
        batch_op.create_index(
            'updated_at_image_idx',
            ['updated_at'],
        )
