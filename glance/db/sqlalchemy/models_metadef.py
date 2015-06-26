# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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
SQLAlchemy models for glance metadata schema
"""

from oslo_db.sqlalchemy import models
from oslo_utils import timeutils
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy.orm import relationship
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint

from glance.db.sqlalchemy.models import JSONEncodedDict


class DictionaryBase(models.ModelBase):
    metadata = None

    def to_dict(self):
        d = {}
        for c in self.__table__.columns:
            d[c.name] = self[c.name]
        return d


BASE_DICT = declarative_base(cls=DictionaryBase)


class GlanceMetadefBase(models.TimestampMixin):
    """Base class for Glance Metadef Models."""

    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'}
    __table_initialized__ = False
    __protected_attributes__ = set(["created_at", "updated_at"])

    created_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=False)
    # TODO(wko): Column `updated_at` have no default value in
    #            openstack common code. We should decide, is this value
    #            required and make changes in oslo (if required) or
    #            in glance (if not).
    updated_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=True, onupdate=lambda: timeutils.utcnow())


class MetadefNamespace(BASE_DICT, GlanceMetadefBase):
    """Represents a metadata-schema namespace in the datastore."""
    __tablename__ = 'metadef_namespaces'
    __table_args__ = (UniqueConstraint('namespace',
                                       name='uq_metadef_namespaces'
                                            '_namespace'),
                      Index('ix_metadef_namespaces_owner', 'owner')
                      )

    id = Column(Integer, primary_key=True, nullable=False)
    namespace = Column(String(80), nullable=False)
    display_name = Column(String(80))
    description = Column(Text())
    visibility = Column(String(32))
    protected = Column(Boolean)
    owner = Column(String(255), nullable=False)


class MetadefObject(BASE_DICT, GlanceMetadefBase):
    """Represents a metadata-schema object in the datastore."""
    __tablename__ = 'metadef_objects'
    __table_args__ = (UniqueConstraint('namespace_id', 'name',
                                       name='uq_metadef_objects_namespace_id'
                                            '_name'),
                      Index('ix_metadef_objects_name', 'name')
                      )

    id = Column(Integer, primary_key=True, nullable=False)
    namespace_id = Column(Integer(), ForeignKey('metadef_namespaces.id'),
                          nullable=False)
    name = Column(String(80), nullable=False)
    description = Column(Text())
    required = Column(Text())
    json_schema = Column(JSONEncodedDict(), default={}, nullable=False)


class MetadefProperty(BASE_DICT, GlanceMetadefBase):
    """Represents a metadata-schema namespace-property in the datastore."""
    __tablename__ = 'metadef_properties'
    __table_args__ = (UniqueConstraint('namespace_id', 'name',
                                       name='uq_metadef_properties_namespace'
                                            '_id_name'),
                      Index('ix_metadef_properties_name', 'name')
                      )

    id = Column(Integer, primary_key=True, nullable=False)
    namespace_id = Column(Integer(), ForeignKey('metadef_namespaces.id'),
                          nullable=False)
    name = Column(String(80), nullable=False)
    json_schema = Column(JSONEncodedDict(), default={}, nullable=False)


class MetadefNamespaceResourceType(BASE_DICT, GlanceMetadefBase):
    """Represents a metadata-schema namespace-property in the datastore."""
    __tablename__ = 'metadef_namespace_resource_types'
    __table_args__ = (Index('ix_metadef_ns_res_types_namespace_id',
                            'namespace_id'),
                      )

    resource_type_id = Column(Integer,
                              ForeignKey('metadef_resource_types.id'),
                              primary_key=True, nullable=False)
    namespace_id = Column(Integer, ForeignKey('metadef_namespaces.id'),
                          primary_key=True, nullable=False)
    properties_target = Column(String(80))
    prefix = Column(String(80))


class MetadefResourceType(BASE_DICT, GlanceMetadefBase):
    """Represents a metadata-schema resource type in the datastore."""
    __tablename__ = 'metadef_resource_types'
    __table_args__ = (UniqueConstraint('name',
                                       name='uq_metadef_resource_types_name'),
                      )

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(80), nullable=False)
    protected = Column(Boolean, nullable=False, default=False)

    associations = relationship(
        "MetadefNamespaceResourceType",
        primaryjoin=id == MetadefNamespaceResourceType.resource_type_id)


class MetadefTag(BASE_DICT, GlanceMetadefBase):
    """Represents a metadata-schema tag in the data store."""
    __tablename__ = 'metadef_tags'
    __table_args__ = (UniqueConstraint('namespace_id', 'name',
                                       name='uq_metadef_tags_namespace_id'
                                            '_name'),
                      Index('ix_metadef_tags_name', 'name')
                      )

    id = Column(Integer, primary_key=True, nullable=False)
    namespace_id = Column(Integer(), ForeignKey('metadef_namespaces.id'),
                          nullable=False)
    name = Column(String(80), nullable=False)


def register_models(engine):
    """Create database tables for all models with the given engine."""
    models = (MetadefNamespace, MetadefObject, MetadefProperty,
              MetadefTag,
              MetadefResourceType, MetadefNamespaceResourceType)
    for model in models:
        model.metadata.create_all(engine)


def unregister_models(engine):
    """Drop database tables for all models with the given engine."""
    models = (MetadefObject, MetadefProperty, MetadefNamespaceResourceType,
              MetadefTag,
              MetadefNamespace, MetadefResourceType)
    for model in models:
        model.metadata.drop_all(engine)
