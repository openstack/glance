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

"""
While SQLAlchemy/sqlalchemy-migrate should abstract this correctly,
there are known issues with these libraries so SQLite and non-SQLite
migrations must be done separately.
"""

import migrate
import sqlalchemy

import glance.common.utils


meta = sqlalchemy.MetaData()
and_ = sqlalchemy.and_
or_ = sqlalchemy.or_


def upgrade(migrate_engine):
    """
    Call the correct dialect-specific upgrade.
    """
    meta.bind = migrate_engine

    t_images = _get_table('images', meta)
    t_image_members = _get_table('image_members', meta)
    t_image_properties = _get_table('image_properties', meta)

    if migrate_engine.url.get_dialect().name == "sqlite":
        _upgrade_sqlite(t_images, t_image_members, t_image_properties)
        _update_all_ids_to_uuids(t_images, t_image_members, t_image_properties)
    else:
        _upgrade_other(t_images, t_image_members, t_image_properties)


def downgrade(migrate_engine):
    """
    Call the correct dialect-specific downgrade.
    """
    meta.bind = migrate_engine

    t_images = _get_table('images', meta)
    t_image_members = _get_table('image_members', meta)
    t_image_properties = _get_table('image_properties', meta)

    if migrate_engine.url.get_dialect().name == "sqlite":
        _downgrade_sqlite(t_images, t_image_members, t_image_properties)
        _update_all_uuids_to_ids(t_images, t_image_members, t_image_properties)
    else:
        _downgrade_other(t_images, t_image_members, t_image_properties)


def _upgrade_sqlite(t_images, t_image_members, t_image_properties):
    """
    Upgrade 011 -> 012 with special SQLite-compatible logic.
    """
    t_images.c.id.alter(sqlalchemy.String(36), primary_key=True)

    sql_commands = [
        """CREATE TABLE image_members_backup (
            id INTEGER NOT NULL,
            image_id VARCHAR(36) NOT NULL,
            member VARCHAR(255) NOT NULL,
            can_share BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME,
            deleted_at DATETIME,
            deleted BOOLEAN NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (image_id, member),
            CHECK (can_share IN (0, 1)),
            CHECK (deleted IN (0, 1)),
            FOREIGN KEY(image_id) REFERENCES images (id)
        );""",
        """INSERT INTO image_members_backup
            SELECT * FROM image_members;""",
        """CREATE TABLE image_properties_backup (
            id INTEGER NOT NULL,
            image_id VARCHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            value TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME,
            deleted_at DATETIME,
            deleted BOOLEAN NOT NULL,
            PRIMARY KEY (id),
            CHECK (deleted IN (0, 1)),
            UNIQUE (image_id, name),
            FOREIGN KEY(image_id) REFERENCES images (id)
        );""",
        """INSERT INTO image_properties_backup
            SELECT * FROM image_properties;""",
    ]

    for command in sql_commands:
        meta.bind.execute(command)

    _sqlite_table_swap(t_image_members, t_image_properties)


def _downgrade_sqlite(t_images, t_image_members, t_image_properties):
    """
    Downgrade 012 -> 011 with special SQLite-compatible logic.
    """
    t_images.c.id.alter(sqlalchemy.Integer(), primary_key=True)

    sql_commands = [
        """CREATE TABLE image_members_backup (
            id INTEGER NOT NULL,
            image_id INTEGER NOT NULL,
            member VARCHAR(255) NOT NULL,
            can_share BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME,
            deleted_at DATETIME,
            deleted BOOLEAN NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (image_id, member),
            CHECK (can_share IN (0, 1)),
            CHECK (deleted IN (0, 1)),
            FOREIGN KEY(image_id) REFERENCES images (id)
        );""",
        """INSERT INTO image_members_backup
            SELECT * FROM image_members;""",
        """CREATE TABLE image_properties_backup (
            id INTEGER NOT NULL,
            image_id INTEGER  NOT NULL,
            name VARCHAR(255) NOT NULL,
            value TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME,
            deleted_at DATETIME,
            deleted BOOLEAN NOT NULL,
            PRIMARY KEY (id),
            CHECK (deleted IN (0, 1)),
            UNIQUE (image_id, name),
            FOREIGN KEY(image_id) REFERENCES images (id)
        );""",
        """INSERT INTO image_properties_backup
            SELECT * FROM image_properties;""",
    ]

    for command in sql_commands:
        meta.bind.execute(command)

    _sqlite_table_swap(t_image_members, t_image_properties)


def _upgrade_other(t_images, t_image_members, t_image_properties):
    """
    Upgrade 011 -> 012 with logic for non-SQLite databases.
    """
    foreign_keys = _get_foreign_keys(t_images,
                                     t_image_members,
                                     t_image_properties)

    for fk in foreign_keys:
        fk.drop()

    t_images.c.id.alter(sqlalchemy.String(36), primary_key=True)
    t_image_members.c.image_id.alter(sqlalchemy.String(36))
    t_image_properties.c.image_id.alter(sqlalchemy.String(36))

    _update_all_ids_to_uuids(t_images, t_image_members, t_image_properties)

    for fk in foreign_keys:
        fk.create()


def _downgrade_other(t_images, t_image_members, t_image_properties):
    """
    Downgrade 012 -> 011 with logic for non-SQLite databases.
    """
    foreign_keys = _get_foreign_keys(t_images,
                                     t_image_members,
                                     t_image_properties)

    for fk in foreign_keys:
        fk.drop()

    t_images.c.id.alter(sqlalchemy.Integer(), primary_key=True)
    t_image_members.c.image_id.alter(sqlalchemy.Integer())
    t_image_properties.c.image_id.alter(sqlalchemy.Integer())

    _update_all_uuids_to_ids(t_images, t_image_members, t_image_properties)

    for fk in foreign_keys:
        fk.create()


def _sqlite_table_swap(t_image_members, t_image_properties):
    t_image_members.drop()
    t_image_properties.drop()

    meta.bind.execute("ALTER TABLE image_members_backup "
                      "RENAME TO image_members")
    meta.bind.execute("ALTER TABLE image_properties_backup "
                      "RENAME TO image_properties")

    for index in t_image_members.indexes.union(t_image_properties.indexes):
        index.create()


def _get_table(table_name, metadata):
    """Return a sqlalchemy Table definition with associated metadata."""
    return sqlalchemy.Table(table_name, metadata, autoload=True)


def _get_foreign_keys(t_images, t_image_members, t_image_properties):
    """Retrieve and return foreign keys for members/properties tables."""
    foreign_keys = []
    if t_image_members.foreign_keys:
        img_members_fk_name = list(t_image_members.foreign_keys)[0].name

        fk1 = migrate.ForeignKeyConstraint([t_image_members.c.image_id],
                                           [t_images.c.id],
                                           name=img_members_fk_name)
        foreign_keys.append(fk1)

    if t_image_properties.foreign_keys:
        img_properties_fk_name = list(t_image_properties.foreign_keys)[0].name

        fk2 = migrate.ForeignKeyConstraint([t_image_properties.c.image_id],
                                           [t_images.c.id],
                                           name=img_properties_fk_name)
        foreign_keys.append(fk2)

    return foreign_keys


def _update_all_ids_to_uuids(t_images, t_image_members, t_image_properties):
    """Transition from INTEGER id to VARCHAR(36) id."""
    images = list(t_images.select().execute())

    for image in images:
        old_id = image["id"]
        new_id = glance.common.utils.generate_uuid()

        t_images.update().\
            where(t_images.c.id == old_id).\
            values(id=new_id).execute()

        t_image_members.update().\
            where(t_image_members.c.image_id == old_id).\
            values(image_id=new_id).execute()

        t_image_properties.update().\
            where(t_image_properties.c.image_id == old_id).\
            values(image_id=new_id).execute()

        t_image_properties.update().\
            where(and_(or_(t_image_properties.c.name == 'kernel_id',
                           t_image_properties.c.name == 'ramdisk_id'),
                       t_image_properties.c.value == old_id)).\
            values(value=new_id).execute()


def _update_all_uuids_to_ids(t_images, t_image_members, t_image_properties):
    """Transition from VARCHAR(36) id to INTEGER id."""
    images = list(t_images.select().execute())

    for image in images:
        old_id = image["id"]
        new_id = 0

        t_images.update().\
            where(t_images.c.id == old_id).\
            values(id=new_id).execute()

        t_image_members.update().\
            where(t_image_members.c.image_id == old_id).\
            values(image_id=new_id).execute()

        t_image_properties.update().\
            where(t_image_properties.c.image_id == old_id).\
            values(image_id=new_id).execute()

        t_image_properties.update().\
            where(and_(or_(t_image_properties.c.name == 'kernel_id',
                           t_image_properties.c.name == 'ramdisk_id'),
                       t_image_properties.c.value == old_id)).\
            values(value=new_id).execute()

        new_id += 1
