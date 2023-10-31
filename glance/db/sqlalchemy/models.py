# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
SQLAlchemy models for glance data
"""

import uuid

from oslo_db.sqlalchemy import models
from oslo_serialization import jsonutils
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import backref, relationship
from sqlalchemy import sql
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy import UniqueConstraint

from glance.common import timeutils


BASE = declarative_base()


class JSONEncodedDict(TypeDecorator):
    """Represents an immutable structure as a json-encoded string"""

    impl = Text

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = jsonutils.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = jsonutils.loads(value)
        return value


class GlanceBase(models.ModelBase, models.TimestampMixin):
    """Base class for Glance Models."""

    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'}
    __table_initialized__ = False
    __protected_attributes__ = set([
        "created_at", "updated_at", "deleted_at", "deleted"])

    def save(self, session=None):
        from glance.db.sqlalchemy import api as db_api
        super(GlanceBase, self).save(session or db_api.get_session())

    created_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=False)
    # TODO(vsergeyev): Column `updated_at` have no default value in
    #                  OpenStack common code. We should decide, is this value
    #                  required and make changes in oslo (if required) or
    #                  in glance (if not).
    updated_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=True, onupdate=lambda: timeutils.utcnow())
    # TODO(boris-42): Use SoftDeleteMixin instead of deleted Column after
    #                 migration that provides UniqueConstraints and change
    #                 type of this column.
    deleted_at = Column(DateTime)
    deleted = Column(Boolean, nullable=False, default=False)

    def delete(self, session=None):
        """Delete this object."""
        self.deleted = True
        self.deleted_at = timeutils.utcnow()
        self.save(session=session)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def to_dict(self):
        d = self.__dict__.copy()
        # NOTE(flaper87): Remove
        # private state instance
        # It is not serializable
        # and causes CircularReference
        d.pop("_sa_instance_state")
        return d


class Image(BASE, GlanceBase):
    """Represents an image in the datastore."""
    __tablename__ = 'images'
    __table_args__ = (Index('checksum_image_idx', 'checksum'),
                      Index('visibility_image_idx', 'visibility'),
                      Index('ix_images_deleted', 'deleted'),
                      Index('owner_image_idx', 'owner'),
                      Index('created_at_image_idx', 'created_at'),
                      Index('updated_at_image_idx', 'updated_at'),
                      Index('os_hidden_image_idx', 'os_hidden'),
                      Index('os_hash_value_image_idx', 'os_hash_value'))

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    name = Column(String(255))
    disk_format = Column(String(20))
    container_format = Column(String(20))
    size = Column(BigInteger().with_variant(Integer, "sqlite"))
    virtual_size = Column(BigInteger().with_variant(Integer, "sqlite"))
    status = Column(String(30), nullable=False)
    visibility = Column(Enum('private', 'public', 'shared', 'community',
                        name='image_visibility'), nullable=False,
                        server_default='shared')
    checksum = Column(String(32))
    os_hash_algo = Column(String(64))
    os_hash_value = Column(String(128))
    min_disk = Column(Integer, nullable=False, default=0)
    min_ram = Column(Integer, nullable=False, default=0)
    owner = Column(String(255))
    protected = Column(Boolean, nullable=False, default=False,
                       server_default=sql.expression.false())
    os_hidden = Column(Boolean, nullable=False, default=False,
                       server_default=sql.expression.false())


class ImageProperty(BASE, GlanceBase):
    """Represents an image properties in the datastore."""
    __tablename__ = 'image_properties'
    __table_args__ = (Index('ix_image_properties_image_id', 'image_id'),
                      Index('ix_image_properties_deleted', 'deleted'),
                      UniqueConstraint('image_id',
                                       'name',
                                       name='ix_image_properties_'
                                            'image_id_name'),)

    id = Column(Integer, primary_key=True)
    image_id = Column(String(36), ForeignKey('images.id'),
                      nullable=False)
    image = relationship(Image, backref=backref('properties'))

    name = Column(String(255), nullable=False)
    value = Column(Text)


class ImageTag(BASE, GlanceBase):
    """Represents an image tag in the datastore."""
    __tablename__ = 'image_tags'
    __table_args__ = (Index('ix_image_tags_image_id', 'image_id'),
                      Index('ix_image_tags_image_id_tag_value',
                            'image_id',
                            'value'),)

    id = Column(Integer, primary_key=True, nullable=False)
    image_id = Column(String(36), ForeignKey('images.id'), nullable=False)
    image = relationship(Image, backref=backref('tags'))
    value = Column(String(255), nullable=False)


class ImageLocation(BASE, GlanceBase):
    """Represents an image location in the datastore."""
    __tablename__ = 'image_locations'
    __table_args__ = (Index('ix_image_locations_image_id', 'image_id'),
                      Index('ix_image_locations_deleted', 'deleted'),)

    id = Column(Integer, primary_key=True, nullable=False)
    image_id = Column(String(36), ForeignKey('images.id'), nullable=False)
    image = relationship(Image, backref=backref('locations'))
    value = Column(Text(), nullable=False)
    meta_data = Column(JSONEncodedDict(), default={})
    status = Column(String(30), server_default='active', nullable=False)


class ImageMember(BASE, GlanceBase):
    """Represents an image members in the datastore."""
    __tablename__ = 'image_members'
    unique_constraint_key_name = 'image_members_image_id_member_deleted_at_key'
    __table_args__ = (Index('ix_image_members_deleted', 'deleted'),
                      Index('ix_image_members_image_id', 'image_id'),
                      Index('ix_image_members_image_id_member',
                            'image_id',
                            'member'),
                      UniqueConstraint('image_id',
                                       'member',
                                       'deleted_at',
                                       name=unique_constraint_key_name),)

    id = Column(Integer, primary_key=True)
    image_id = Column(String(36), ForeignKey('images.id'),
                      nullable=False)
    image = relationship(Image, backref=backref('members'))

    member = Column(String(255), nullable=False)
    can_share = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="pending",
                    server_default='pending')


class Task(BASE, GlanceBase):
    """Represents an task in the datastore"""
    __tablename__ = 'tasks'
    __table_args__ = (Index('ix_tasks_type', 'type'),
                      Index('ix_tasks_status', 'status'),
                      Index('ix_tasks_owner', 'owner'),
                      Index('ix_tasks_deleted', 'deleted'),
                      Index('ix_tasks_image_id', 'image_id'),
                      Index('ix_tasks_updated_at', 'updated_at'))

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    type = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False)
    owner = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    image_id = Column(String(36), nullable=True)
    request_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True)


class TaskInfo(BASE, models.ModelBase):
    """Represents task info in the datastore"""
    __tablename__ = 'task_info'

    task_id = Column(String(36),
                     ForeignKey('tasks.id'),
                     primary_key=True,
                     nullable=False)

    task = relationship(Task, backref=backref('info', uselist=False))

    # NOTE(nikhil): input and result are stored as text in the DB.
    # SQLAlchemy marshals the data to/from JSON using custom type
    # JSONEncodedDict. It uses simplejson underneath.
    input = Column(JSONEncodedDict())
    result = Column(JSONEncodedDict())
    message = Column(Text)


class NodeReference(BASE, models.ModelBase):
    """Represents node info in the datastore"""
    __tablename__ = 'node_reference'
    __table_args__ = (UniqueConstraint(
        'node_reference_url',
        name='uq_node_reference_node_reference_url'),)

    node_reference_id = Column(BigInteger().with_variant(Integer, 'sqlite'),
                               primary_key=True,
                               nullable=False, autoincrement=True)
    node_reference_url = Column(String(length=255),
                                nullable=False)


class CachedImages(BASE, models.ModelBase):
    """Represents an image tag in the datastore."""
    __tablename__ = 'cached_images'
    __table_args__ = (UniqueConstraint(
        'image_id',
        'node_reference_id',
        name='ix_cached_images_image_id_node_reference_id'),)

    id = Column(BigInteger().with_variant(Integer, 'sqlite'),
                primary_key=True, autoincrement=True,
                nullable=False)
    image_id = Column(String(36), nullable=False)
    last_accessed = Column(DateTime, nullable=False)
    last_modified = Column(DateTime, nullable=False)
    size = Column(BigInteger(), nullable=False)
    hits = Column(Integer, nullable=False)
    checksum = Column(String(32), nullable=True)
    node_reference_id = Column(
        BigInteger().with_variant(Integer, 'sqlite'),
        ForeignKey('node_reference.node_reference_id'),
        nullable=False)


def register_models(engine):
    """Create database tables for all models with the given engine."""
    models = (Image, ImageProperty, ImageMember)
    for model in models:
        model.metadata.create_all(engine)


def unregister_models(engine):
    """Drop database tables for all models with the given engine."""
    models = (Image, ImageProperty)
    for model in models:
        model.metadata.drop_all(engine)
