# Copyright 2013 OpenStack Foundation
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

from sqlalchemy import MetaData, Table, Column, String


meta = MetaData()

status = Column('status', String(20), default="pending")


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    image_members = Table('image_members', meta, autoload=True)
    image_members.create_column(status)


def downgrade(migrate_engine):
    meta.bind = migrate_engine

    image_members = Table('image_members', meta, autoload=True)
    image_members.drop_column(status)
