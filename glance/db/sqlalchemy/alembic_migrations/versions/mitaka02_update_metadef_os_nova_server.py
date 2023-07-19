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

"""update metadef os_nova_server

Revision ID: mitaka02
Revises: mitaka01
Create Date: 2016-08-03 17:23:23.041663

"""

from alembic import op
from sqlalchemy import MetaData, Table


# revision identifiers, used by Alembic.
revision = 'mitaka02'
down_revision = 'mitaka01'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    meta = MetaData()

    resource_types_table = Table(
        'metadef_resource_types', meta, autoload_with=bind)

    op.execute(
        resource_types_table.update().where(
            resource_types_table.c.name == 'OS::Nova::Instance'
        ).values(name='OS::Nova::Server')
    )
