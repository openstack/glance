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

"""add visibility to images

Revision ID: ocata_expand01
Revises: mitaka02
Create Date: 2017-01-27 12:58:16.647499

"""

from alembic import op
from sqlalchemy import Column, Enum, MetaData, Table

from glance.cmd import manage
from glance.db import migration

# revision identifiers, used by Alembic.
revision = 'ocata_expand01'
down_revision = 'mitaka02'
branch_labels = migration.EXPAND_BRANCH
depends_on = None

ERROR_MESSAGE = 'Invalid visibility value'
MYSQL_INSERT_TRIGGER = """
CREATE TRIGGER insert_visibility BEFORE INSERT ON images
FOR EACH ROW
BEGIN
    -- NOTE(abashmak):
    -- The following IF/ELSE block implements a priority decision tree.
    -- Strict order MUST be followed to correctly cover all the edge cases.

    -- Edge case: neither is_public nor visibility specified
    --            (or both specified as NULL):
    IF NEW.is_public <=> NULL AND NEW.visibility <=> NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
    -- Edge case: both is_public and visibility specified:
    ELSEIF NOT(NEW.is_public <=> NULL OR NEW.visibility <=> NULL) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
    -- Inserting with is_public, set visibility accordingly:
    ELSEIF NOT NEW.is_public <=> NULL THEN
        IF NEW.is_public = 1 THEN
            SET NEW.visibility = 'public';
        ELSE
            SET NEW.visibility = 'shared';
        END IF;
    -- Inserting with visibility, set is_public accordingly:
    ELSEIF NOT NEW.visibility <=> NULL THEN
        IF NEW.visibility = 'public' THEN
            SET NEW.is_public = 1;
        ELSE
            SET NEW.is_public = 0;
        END IF;
    -- Edge case: either one of: is_public or visibility,
    --            is explicitly set to NULL:
    ELSE
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
    END IF;
END;
"""

MYSQL_UPDATE_TRIGGER = """
CREATE TRIGGER update_visibility BEFORE UPDATE ON images
FOR EACH ROW
BEGIN
    -- Case: new value specified for is_public:
    IF NOT NEW.is_public <=> OLD.is_public THEN
        -- Edge case: is_public explicitly set to NULL:
        IF NEW.is_public <=> NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
        -- Edge case: new value also specified for visibility
        ELSEIF NOT NEW.visibility <=> OLD.visibility THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
        -- Case: visibility not specified or specified as OLD value:
        -- NOTE(abashmak): There is no way to reliably determine which
        -- of the above two cases occurred, but allowing to proceed with
        -- the update in either case does not break the model for both
        -- N and N-1 services.
        ELSE
            -- Set visibility according to the value of is_public:
            IF NEW.is_public <=> 1 THEN
                SET NEW.visibility = 'public';
            ELSE
                SET NEW.visibility = 'shared';
            END IF;
        END IF;
    -- Case: new value specified for visibility:
    ELSEIF NOT NEW.visibility <=> OLD.visibility THEN
        -- Edge case: visibility explicitly set to NULL:
        IF NEW.visibility <=> NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
        -- Edge case: new value also specified for is_public
        ELSEIF NOT NEW.is_public <=> OLD.is_public THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '%s';
        -- Case: is_public not specified or specified as OLD value:
        -- NOTE(abashmak): There is no way to reliably determine which
        -- of the above two cases occurred, but allowing to proceed with
        -- the update in either case does not break the model for both
        -- N and N-1 services.
        ELSE
            -- Set is_public according to the value of visibility:
            IF NEW.visibility <=> 'public' THEN
                SET NEW.is_public = 1;
            ELSE
                SET NEW.is_public = 0;
            END IF;
        END IF;
    END IF;
END;
"""


def _add_visibility_column(meta):
    enum = Enum('private', 'public', 'shared', 'community', metadata=meta,
                name='image_visibility')
    enum.create()
    v_col = Column('visibility', enum, nullable=True, server_default=None)
    op.add_column('images', v_col)
    op.create_index('visibility_image_idx', 'images', ['visibility'])


def _add_triggers(engine):
    if engine.engine.name == 'mysql':
        op.execute(MYSQL_INSERT_TRIGGER % (ERROR_MESSAGE, ERROR_MESSAGE,
                                           ERROR_MESSAGE))
        op.execute(MYSQL_UPDATE_TRIGGER % (ERROR_MESSAGE, ERROR_MESSAGE,
                                           ERROR_MESSAGE, ERROR_MESSAGE))


def _change_nullability_and_default_on_is_public(meta):
    # NOTE(hemanthm): we mark is_public as nullable so that when new versions
    # add data only to be visibility column, is_public can be null.
    images = Table('images', meta, autoload=True)
    images.c.is_public.alter(nullable=True, server_default=None)


def upgrade():
    migrate_engine = op.get_bind()
    meta = MetaData(bind=migrate_engine)

    _add_visibility_column(meta)
    _change_nullability_and_default_on_is_public(meta)
    if manage.USE_TRIGGERS:
        _add_triggers(migrate_engine)
