# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import uuid

from oslo_db.sqlalchemy import models
from oslo_utils import timeutils
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy.ext import declarative
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy.orm import backref
from sqlalchemy.orm import composite
from sqlalchemy.orm import relationship
from sqlalchemy import String
from sqlalchemy import Text

import glance.artifacts as ga
from glance.common import semver_db
from glance import i18n
from oslo_log import log as os_logging

BASE = declarative.declarative_base()
LOG = os_logging.getLogger(__name__)
_LW = i18n._LW


class ArtifactBase(models.ModelBase, models.TimestampMixin):
    """Base class for Artifact Models."""

    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'}
    __table_initialized__ = False
    __protected_attributes__ = set([
        "created_at", "updated_at"])

    created_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=False)

    updated_at = Column(DateTime, default=lambda: timeutils.utcnow(),
                        nullable=False, onupdate=lambda: timeutils.utcnow())

    def save(self, session=None):
        from glance.db.sqlalchemy import api as db_api

        super(ArtifactBase, self).save(session or db_api.get_session())

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def to_dict(self):
        d = {}
        for c in self.__table__.columns:
            d[c.name] = self[c.name]
        return d


def _parse_property_type_value(prop, show_text_properties=True):
    columns = [
        'int_value',
        'string_value',
        'bool_value',
        'numeric_value']
    if show_text_properties:
        columns.append('text_value')

    for prop_type in columns:
        if getattr(prop, prop_type) is not None:
            return prop_type.rpartition('_')[0], getattr(prop, prop_type)

    return None, None


class Artifact(BASE, ArtifactBase):
    __tablename__ = 'artifacts'
    __table_args__ = (
        Index('ix_artifact_name_and_version', 'name', 'version_prefix',
              'version_suffix'),
        Index('ix_artifact_type', 'type_name', 'type_version_prefix',
              'type_version_suffix'),
        Index('ix_artifact_state', 'state'),
        Index('ix_artifact_owner', 'owner'),
        Index('ix_artifact_visibility', 'visibility'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'})

    __protected_attributes__ = ArtifactBase.__protected_attributes__.union(
        set(['published_at', 'deleted_at']))

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    type_name = Column(String(255), nullable=False)
    type_version_prefix = Column(BigInteger, nullable=False)
    type_version_suffix = Column(String(255))
    type_version_meta = Column(String(255))
    type_version = composite(semver_db.DBVersion, type_version_prefix,
                             type_version_suffix, type_version_meta,
                             comparator_factory=semver_db.VersionComparator)
    version_prefix = Column(BigInteger, nullable=False)
    version_suffix = Column(String(255))
    version_meta = Column(String(255))
    version = composite(semver_db.DBVersion, version_prefix,
                        version_suffix, version_meta,
                        comparator_factory=semver_db.VersionComparator)
    description = Column(Text)
    visibility = Column(String(32), nullable=False)
    state = Column(String(32), nullable=False)
    owner = Column(String(255), nullable=False)
    published_at = Column(DateTime)
    deleted_at = Column(DateTime)

    def to_dict(self, show_level=ga.Showlevel.BASIC,
                show_text_properties=True):
        d = super(Artifact, self).to_dict()

        d.pop('type_version_prefix')
        d.pop('type_version_suffix')
        d.pop('type_version_meta')
        d.pop('version_prefix')
        d.pop('version_suffix')
        d.pop('version_meta')
        d['type_version'] = str(self.type_version)
        d['version'] = str(self.version)

        tags = []
        for tag in self.tags:
            tags.append(tag.value)
        d['tags'] = tags

        if show_level == ga.Showlevel.NONE:
            return d

        properties = {}

        # sort properties
        self.properties.sort(key=lambda elem: (elem.name, elem.position))

        for prop in self.properties:
            proptype, propvalue = _parse_property_type_value(
                prop, show_text_properties)
            if proptype is None:
                continue

            if prop.position is not None:
                # make array
                for p in properties.keys():
                    if p == prop.name:
                        # add value to array
                        properties[p]['value'].append(dict(type=proptype,
                                                           value=propvalue))
                        break
                else:
                    # create new array
                    p = dict(type='array',
                             value=[])
                    p['value'].append(dict(type=proptype,
                                           value=propvalue))
                    properties[prop.name] = p
            else:
                # make scalar
                properties[prop.name] = dict(type=proptype,
                                             value=propvalue)
        d['properties'] = properties

        blobs = {}
        # sort blobs
        self.blobs.sort(key=lambda elem: elem.position)

        for blob in self.blobs:
            locations = []
            # sort locations
            blob.locations.sort(key=lambda elem: elem.position)
            for loc in blob.locations:
                locations.append(dict(value=loc.value,
                                      status=loc.status))
            if blob.name in blobs:
                blobs[blob.name].append(dict(size=blob.size,
                                             checksum=blob.checksum,
                                             locations=locations,
                                             item_key=blob.item_key))
            else:
                blobs[blob.name] = []
                blobs[blob.name].append(dict(size=blob.size,
                                             checksum=blob.checksum,
                                             locations=locations,
                                             item_key=blob.item_key))

        d['blobs'] = blobs

        return d


class ArtifactDependency(BASE, ArtifactBase):
    __tablename__ = 'artifact_dependencies'
    __table_args__ = (Index('ix_artifact_dependencies_source_id',
                            'artifact_source'),
                      Index('ix_artifact_dependencies_origin_id',
                            'artifact_origin'),
                      Index('ix_artifact_dependencies_dest_id',
                            'artifact_dest'),
                      Index('ix_artifact_dependencies_direct_dependencies',
                            'artifact_source', 'is_direct'),
                      {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'})

    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: str(uuid.uuid4()))
    artifact_source = Column(String(36), ForeignKey('artifacts.id'),
                             nullable=False)
    artifact_dest = Column(String(36), ForeignKey('artifacts.id'),
                           nullable=False)
    artifact_origin = Column(String(36), ForeignKey('artifacts.id'),
                             nullable=False)
    is_direct = Column(Boolean, nullable=False)
    position = Column(Integer)
    name = Column(String(36))

    source = relationship('Artifact',
                          backref=backref('dependencies', cascade="all, "
                                                                  "delete"),
                          foreign_keys="ArtifactDependency.artifact_source")
    dest = relationship('Artifact',
                        foreign_keys="ArtifactDependency.artifact_dest")
    origin = relationship('Artifact',
                          foreign_keys="ArtifactDependency.artifact_origin")


class ArtifactTag(BASE, ArtifactBase):
    __tablename__ = 'artifact_tags'
    __table_args__ = (Index('ix_artifact_tags_artifact_id', 'artifact_id'),
                      Index('ix_artifact_tags_artifact_id_tag_value',
                            'artifact_id', 'value'),
                      {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)

    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: str(uuid.uuid4()))
    artifact_id = Column(String(36), ForeignKey('artifacts.id'),
                         nullable=False)
    artifact = relationship(Artifact,
                            backref=backref('tags',
                                            cascade="all, delete-orphan"))
    value = Column(String(255), nullable=False)


class ArtifactProperty(BASE, ArtifactBase):
    __tablename__ = 'artifact_properties'
    __table_args__ = (
        Index('ix_artifact_properties_artifact_id', 'artifact_id'),
        Index('ix_artifact_properties_name', 'name'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)
    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: str(uuid.uuid4()))
    artifact_id = Column(String(36), ForeignKey('artifacts.id'),
                         nullable=False)
    artifact = relationship(Artifact,
                            backref=backref('properties',
                                            cascade="all, delete-orphan"))
    name = Column(String(255), nullable=False)
    string_value = Column(String(255))
    int_value = Column(Integer)
    numeric_value = Column(Numeric)
    bool_value = Column(Boolean)
    text_value = Column(Text)
    position = Column(Integer)


class ArtifactBlob(BASE, ArtifactBase):
    __tablename__ = 'artifact_blobs'
    __table_args__ = (
        Index('ix_artifact_blobs_artifact_id', 'artifact_id'),
        Index('ix_artifact_blobs_name', 'name'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'},)
    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: str(uuid.uuid4()))
    artifact_id = Column(String(36), ForeignKey('artifacts.id'),
                         nullable=False)
    name = Column(String(255), nullable=False)
    item_key = Column(String(329))
    size = Column(BigInteger(), nullable=False)
    checksum = Column(String(32))
    position = Column(Integer)
    artifact = relationship(Artifact,
                            backref=backref('blobs',
                                            cascade="all, delete-orphan"))


class ArtifactBlobLocation(BASE, ArtifactBase):
    __tablename__ = 'artifact_blob_locations'
    __table_args__ = (Index('ix_artifact_blob_locations_blob_id',
                            'blob_id'),
                      {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8'})

    id = Column(String(36), primary_key=True, nullable=False,
                default=lambda: str(uuid.uuid4()))
    blob_id = Column(String(36), ForeignKey('artifact_blobs.id'),
                     nullable=False)
    value = Column(Text, nullable=False)
    position = Column(Integer)
    status = Column(String(36), default='active', nullable=True)
    blob = relationship(ArtifactBlob,
                        backref=backref('locations',
                                        cascade="all, delete-orphan"))


def register_models(engine):
    """Create database tables for all models with the given engine."""
    models = (Artifact, ArtifactTag, ArtifactProperty,
              ArtifactBlob, ArtifactBlobLocation, ArtifactDependency)
    for model in models:
        model.metadata.create_all(engine)


def unregister_models(engine):
    """Drop database tables for all models with the given engine."""
    models = (ArtifactDependency, ArtifactBlobLocation, ArtifactBlob,
              ArtifactProperty, ArtifactTag, Artifact)
    for model in models:
        model.metadata.drop_all(engine)
