# Copyright 2016 Rackspace
# Copyright 2016 Intel Corporation
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

from sqlalchemy import MetaData, select, Table, and_, not_


def has_migrations(engine):
    """Returns true if at least one data row can be migrated.

    There are rows left to migrate if:
     #1 There exists a row with visibility not set yet.
        Or
     #2 There exists a private image with active members but its visibility
        isn't set to 'shared' yet.

    Note: This method can return a false positive if data migrations
    are running in the background as it's being called.
    """
    meta = MetaData(engine)
    images = Table('images', meta, autoload=True)

    rows_with_null_visibility = (select([images.c.id])
                                 .where(images.c.visibility == None)
                                 .limit(1)
                                 .execute())

    if rows_with_null_visibility.rowcount == 1:
        return True

    image_members = Table('image_members', meta, autoload=True)
    rows_with_pending_shared = (select([images.c.id])
                                .where(and_(
                                    images.c.visibility == 'private',
                                    images.c.id.in_(
                                        select([image_members.c.image_id])
                                        .distinct()
                                        .where(not_(image_members.c.deleted))))
                                       )
                                .limit(1)
                                .execute())
    if rows_with_pending_shared.rowcount == 1:
        return True

    return False


def _mark_all_public_images_with_public_visibility(images):
    migrated_rows = (images
                     .update().values(visibility='public')
                     .where(images.c.is_public)
                     .execute())
    return migrated_rows.rowcount


def _mark_all_non_public_images_with_private_visibility(images):
    migrated_rows = (images
                     .update().values(visibility='private')
                     .where(not_(images.c.is_public))
                     .execute())
    return migrated_rows.rowcount


def _mark_all_private_images_with_members_as_shared_visibility(images,
                                                               image_members):
    migrated_rows = (images
                     .update().values(visibility='shared')
                     .where(and_(images.c.visibility == 'private',
                                 images.c.id.in_(
                                     select([image_members.c.image_id])
                                     .distinct()
                                     .where(not_(image_members.c.deleted)))))
                     .execute())
    return migrated_rows.rowcount


def _migrate_all(engine):
    meta = MetaData(engine)
    images = Table('images', meta, autoload=True)
    image_members = Table('image_members', meta, autoload=True)

    num_rows = _mark_all_public_images_with_public_visibility(images)
    num_rows += _mark_all_non_public_images_with_private_visibility(images)
    num_rows += _mark_all_private_images_with_members_as_shared_visibility(
        images, image_members)

    return num_rows


def migrate(engine):
    """Set visibility column based on is_public and image members."""
    return _migrate_all(engine)
