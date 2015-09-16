# Copyright 2013 Rackspace Hosting
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

from sqlalchemy import MetaData, Table, Index

INDEX_NAME = 'owner_image_idx'


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    images = Table('images', meta, autoload=True)

    index = Index(INDEX_NAME, images.c.owner)
    index.create(migrate_engine)
