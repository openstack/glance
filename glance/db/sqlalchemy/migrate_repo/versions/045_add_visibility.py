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

from sqlalchemy import Column, Enum, Index, MetaData, Table, select, not_, and_
from sqlalchemy.engine import reflection


def upgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)

    images = Table('images', meta, autoload=True)

    enum = Enum('private', 'public', 'shared', 'community', metadata=meta,
                name='image_visibility')
    enum.create()

    images.create_column(Column('visibility', enum, nullable=False,
                                server_default='shared'))
    visibility_index = Index('visibility_image_idx', images.c.visibility)
    visibility_index.create(migrate_engine)

    images.update(values={'visibility': 'public'}).where(
        images.c.is_public).execute()

    image_members = Table('image_members', meta, autoload=True)

    # NOTE(dharinic): Mark all the non-public images as 'private' first
    images.update().values(visibility='private').where(
        not_(images.c.is_public)).execute()
    # NOTE(dharinic): Identify 'shared' images from the above
    images.update().values(visibility='shared').where(and_(
        images.c.visibility == 'private', images.c.id.in_(select(
            [image_members.c.image_id]).distinct().where(
                not_(image_members.c.deleted))))).execute()

    insp = reflection.Inspector.from_engine(migrate_engine)
    for index in insp.get_indexes('images'):
        if 'ix_images_is_public' == index['name']:
            Index('ix_images_is_public', images.c.is_public).drop()
            break

    images.c.is_public.drop()
