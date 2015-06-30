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

CREATED_AT_INDEX = 'created_at_image_idx'
UPDATED_AT_INDEX = 'updated_at_image_idx'


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    images = Table('images', meta, autoload=True)

    created_index = Index(CREATED_AT_INDEX, images.c.created_at)
    created_index.create(migrate_engine)
    updated_index = Index(UPDATED_AT_INDEX, images.c.updated_at)
    updated_index.create(migrate_engine)
