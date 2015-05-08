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
from oslo_utils import timeutils
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy.orm import backref, relationship
from sqlalchemy import sql
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy import UniqueConstraint


BASE = declarative_base()


@compiles(BigInteger, 'sqlite')
def compile_big_int_sqlite(type_, compiler, **kw):
    return 'INTEGER'


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
    #                  openstack common code. We should decide, is this value
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
                      Index('ix_images_is_public', 'is_public'),
                      Index('ix_images_deleted', 'deleted'),
                      Index('owner_image_idx', 'owner'),)

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    name = Column(String(255))
    disk_format = Column(String(20))
    container_format = Column(String(20))
    size = Column(BigInteger)
    virtual_size = Column(BigInteger)
    status = Column(String(30), nullable=False)
    is_public = Column(Boolean, nullable=False, default=False)
    checksum = Column(String(32))
    min_disk = Column(Integer, nullable=False, default=0)
    min_ram = Column(Integer, nullable=False, default=0)
    owner = Column(String(255))
    protected = Column(Boolean, nullable=False, default=False,
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
                      Index('ix_tasks_updated_at', 'updated_at'))

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    type = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False)
    owner = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=True)


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
