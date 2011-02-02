# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import logging
from sqlalchemy.schema import (MetaData, Table, Column)

from glance.registry.db.migrate_repo.schema import (String,
                                                    Boolean,
                                                    Text,
                                                    DateTime,
                                                    Integer)


meta = MetaData()


images = Table('images', meta,
    Column('id', Integer(),  primary_key=True, nullable=False),
    Column('name', String(255)),
    Column('type', String(30)),
    Column('size', Integer()),
    Column('status', String(30), nullable=False),
    Column('is_public', Boolean(), nullable=False, default=False),
    Column('location', Text()),
    Column('created_at', DateTime(), nullable=False),
    Column('updated_at', DateTime()),
    Column('deleted_at', DateTime()),
    Column('deleted', Boolean(), nullable=False, default=False))


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    images.create()


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    images.drop()
