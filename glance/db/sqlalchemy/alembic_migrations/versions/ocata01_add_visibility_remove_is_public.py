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

"""add visibility to and remove is_public from images

Revision ID: ocata01
Revises: mitaka02
Create Date: 2017-01-20 12:58:16.647499

"""

import os

from alembic import op
from sqlalchemy import Column, Enum, MetaData, select, Table, not_, and_
import sqlparse

# revision identifiers, used by Alembic.
revision = 'ocata01'
down_revision = 'mitaka02'
branch_labels = None
depends_on = None


def upgrade():
    migrate_engine = op.get_bind()
    meta = MetaData(bind=migrate_engine)

    engine_name = migrate_engine.engine.name
    if engine_name == 'sqlite':
        sql_file = os.path.splitext(__file__)[0]
        sql_file += '.sql'
        with open(sql_file, 'r') as sqlite_script:
            sql = sqlparse.format(sqlite_script.read(), strip_comments=True)
            for statement in sqlparse.split(sql):
                op.execute(statement)
        return

    enum = Enum('private', 'public', 'shared', 'community', metadata=meta,
                name='image_visibility')
    enum.create()
    v_col = Column('visibility', enum, nullable=False, server_default='shared')
    op.add_column('images', v_col)

    op.create_index('visibility_image_idx', 'images', ['visibility'])

    images = Table('images', meta, autoload=True)
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

    op.drop_index('ix_images_is_public', 'images')
    op.drop_column('images', 'is_public')
