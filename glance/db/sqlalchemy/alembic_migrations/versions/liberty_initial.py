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

"""liberty initial

Revision ID: liberty
Revises:
Create Date: 2016-08-03 16:06:59.657433

"""

from glance.db.sqlalchemy.alembic_migrations import add_artifacts_tables
from glance.db.sqlalchemy.alembic_migrations import add_images_tables
from glance.db.sqlalchemy.alembic_migrations import add_metadefs_tables
from glance.db.sqlalchemy.alembic_migrations import add_tasks_tables

# revision identifiers, used by Alembic.
revision = 'liberty'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    add_images_tables.upgrade()
    add_tasks_tables.upgrade()
    add_metadefs_tables.upgrade()
    add_artifacts_tables.upgrade()
