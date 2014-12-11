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

import sqlalchemy
from sqlalchemy import Table, Index, UniqueConstraint, Sequence
from sqlalchemy.schema import (AddConstraint, DropConstraint, CreateIndex,
                               ForeignKeyConstraint)
from sqlalchemy import sql
from sqlalchemy import update


def upgrade(migrate_engine):
    meta = sqlalchemy.MetaData()
    meta.bind = migrate_engine

    if migrate_engine.name not in ['mysql', 'postgresql']:
        return

    image_properties = Table('image_properties', meta, autoload=True)
    image_members = Table('image_members', meta, autoload=True)
    images = Table('images', meta, autoload=True)

    # We have to ensure that we doesn't have `nulls` values since we are going
    # to set nullable=False
    migrate_engine.execute(
        update(image_members)
        .where(image_members.c.status == sql.expression.null())
        .values(status='pending'))

    migrate_engine.execute(
        update(images)
        .where(images.c.protected == sql.expression.null())
        .values(protected=sql.expression.false()))

    image_members.c.status.alter(nullable=False, server_default='pending')
    images.c.protected.alter(
        nullable=False, server_default=sql.expression.false())

    if migrate_engine.name == 'postgresql':
        Index('ix_image_properties_image_id_name',
              image_properties.c.image_id,
              image_properties.c.name).drop()

        # We have different names of this constraint in different versions of
        # postgresql. Since we have only one constraint on this table, we can
        # get it in the following way.
        name = migrate_engine.execute(
            """SELECT conname
               FROM pg_constraint
               WHERE conrelid =
                   (SELECT oid
                    FROM pg_class
                    WHERE relname LIKE 'image_properties')
                  AND contype = 'u';""").scalar()

        constraint = UniqueConstraint(image_properties.c.image_id,
                                      image_properties.c.name,
                                      name='%s' % name)
        migrate_engine.execute(DropConstraint(constraint))

        constraint = UniqueConstraint(image_properties.c.image_id,
                                      image_properties.c.name,
                                      name='ix_image_properties_image_id_name')
        migrate_engine.execute(AddConstraint(constraint))

        images.c.id.alter(server_default=None)
    if migrate_engine.name == 'mysql':
        constraint = UniqueConstraint(image_properties.c.image_id,
                                      image_properties.c.name,
                                      name='image_id')
        migrate_engine.execute(DropConstraint(constraint))
        image_locations = Table('image_locations', meta, autoload=True)
        if len(image_locations.foreign_keys) == 0:
            migrate_engine.execute(AddConstraint(ForeignKeyConstraint(
                [image_locations.c.image_id], [images.c.id])))


def downgrade(migrate_engine):
    meta = sqlalchemy.MetaData()
    meta.bind = migrate_engine

    if migrate_engine.name not in ['mysql', 'postgresql']:
        return

    image_properties = Table('image_properties', meta, autoload=True)
    image_members = Table('image_members', meta, autoload=True)
    images = Table('images', meta, autoload=True)

    if migrate_engine.name == 'postgresql':
        constraint = UniqueConstraint(image_properties.c.image_id,
                                      image_properties.c.name,
                                      name='ix_image_properties_image_id_name')
        migrate_engine.execute(DropConstraint(constraint))

        constraint = UniqueConstraint(image_properties.c.image_id,
                                      image_properties.c.name)
        migrate_engine.execute(AddConstraint(constraint))

        index = Index('ix_image_properties_image_id_name',
                      image_properties.c.image_id,
                      image_properties.c.name)
        migrate_engine.execute(CreateIndex(index))

        images.c.id.alter(server_default=Sequence('images_id_seq')
                          .next_value())

    if migrate_engine.name == 'mysql':
        constraint = UniqueConstraint(image_properties.c.image_id,
                                      image_properties.c.name,
                                      name='image_id')
        migrate_engine.execute(AddConstraint(constraint))

    image_members.c.status.alter(nullable=True, server_default=None)
    images.c.protected.alter(nullable=True, server_default=None)
