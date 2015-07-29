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

from sqlalchemy.schema import (Column, ForeignKey, Index, MetaData, Table)


from glance.db.sqlalchemy.migrate_repo.schema import (
    BigInteger, Boolean, DateTime, Integer, Numeric, String, Text,
    create_tables)  # noqa


def define_artifacts_table(meta):
    artifacts = Table('artifacts',
                      meta,
                      Column('id', String(36), primary_key=True,
                             nullable=False),
                      Column('name', String(255), nullable=False),
                      Column('type_name', String(255), nullable=False),
                      Column('type_version_prefix', BigInteger(),
                             nullable=False),
                      Column('type_version_suffix', String(255)),
                      Column('type_version_meta', String(255)),
                      Column('version_prefix', BigInteger(), nullable=False),
                      Column('version_suffix', String(255)),
                      Column('version_meta', String(255)),
                      Column('description', Text()),
                      Column('visibility', String(32), nullable=False),
                      Column('state', String(32), nullable=False),
                      Column('owner', String(255), nullable=False),
                      Column('created_at', DateTime(), nullable=False),
                      Column('updated_at', DateTime(),
                             nullable=False),
                      Column('deleted_at', DateTime()),
                      Column('published_at', DateTime()),
                      mysql_engine='InnoDB',
                      mysql_charset='utf8',
                      extend_existing=True)

    Index('ix_artifact_name_and_version', artifacts.c.name,
          artifacts.c.version_prefix, artifacts.c.version_suffix)
    Index('ix_artifact_type', artifacts.c.type_name,
          artifacts.c.type_version_prefix, artifacts.c.type_version_suffix)
    Index('ix_artifact_state', artifacts.c.state)
    Index('ix_artifact_owner', artifacts.c.owner)
    Index('ix_artifact_visibility', artifacts.c.visibility)

    return artifacts


def define_artifact_tags_table(meta):
    artifact_tags = Table('artifact_tags',
                          meta,
                          Column('id', String(36), primary_key=True,
                                 nullable=False),
                          Column('artifact_id', String(36),
                                 ForeignKey('artifacts.id'), nullable=False),
                          Column('value', String(255), nullable=False),
                          Column('created_at', DateTime(), nullable=False),
                          Column('updated_at', DateTime(),
                                 nullable=False),
                          mysql_engine='InnoDB',
                          mysql_charset='utf8',
                          extend_existing=True)

    Index('ix_artifact_tags_artifact_id', artifact_tags.c.artifact_id)
    Index('ix_artifact_tags_artifact_id_tag_value',
          artifact_tags.c.artifact_id, artifact_tags.c.value)

    return artifact_tags


def define_artifact_dependencies_table(meta):
    artifact_dependencies = Table('artifact_dependencies',
                                  meta,
                                  Column('id', String(36), primary_key=True,
                                         nullable=False),
                                  Column('artifact_source', String(36),
                                         ForeignKey('artifacts.id'),
                                         nullable=False),
                                  Column('artifact_dest', String(36),
                                         ForeignKey('artifacts.id'),
                                         nullable=False),
                                  Column('artifact_origin', String(36),
                                         ForeignKey('artifacts.id'),
                                         nullable=False),
                                  Column('is_direct', Boolean(),
                                         nullable=False),
                                  Column('position', Integer()),
                                  Column('name', String(36)),
                                  Column('created_at', DateTime(),
                                         nullable=False),
                                  Column('updated_at', DateTime(),
                                         nullable=False),
                                  mysql_engine='InnoDB',
                                  mysql_charset='utf8',
                                  extend_existing=True)

    Index('ix_artifact_dependencies_source_id',
          artifact_dependencies.c.artifact_source)
    Index('ix_artifact_dependencies_dest_id',
          artifact_dependencies.c.artifact_dest),
    Index('ix_artifact_dependencies_origin_id',
          artifact_dependencies.c.artifact_origin)
    Index('ix_artifact_dependencies_direct_dependencies',
          artifact_dependencies.c.artifact_source,
          artifact_dependencies.c.is_direct)
    return artifact_dependencies


def define_artifact_blobs_table(meta):
    artifact_blobs = Table('artifact_blobs',
                           meta,
                           Column('id', String(36), primary_key=True,
                                  nullable=False),
                           Column('artifact_id', String(36),
                                  ForeignKey('artifacts.id'),
                                  nullable=False),
                           Column('size', BigInteger(), nullable=False),
                           Column('checksum', String(32)),
                           Column('name', String(255), nullable=False),
                           Column('item_key', String(329)),
                           Column('position', Integer()),
                           Column('created_at', DateTime(), nullable=False),
                           Column('updated_at', DateTime(),
                                  nullable=False),
                           mysql_engine='InnoDB',
                           mysql_charset='utf8',
                           extend_existing=True)
    Index('ix_artifact_blobs_artifact_id',
          artifact_blobs.c.artifact_id)
    Index('ix_artifact_blobs_name',
          artifact_blobs.c.name)
    return artifact_blobs


def define_artifact_properties_table(meta):
    artifact_properties = Table('artifact_properties',
                                meta,
                                Column('id', String(36),
                                       primary_key=True,
                                       nullable=False),
                                Column('artifact_id', String(36),
                                       ForeignKey('artifacts.id'),
                                       nullable=False),
                                Column('name', String(255),
                                       nullable=False),
                                Column('string_value', String(255)),
                                Column('int_value', Integer()),
                                Column('numeric_value', Numeric()),
                                Column('bool_value', Boolean()),
                                Column('text_value', Text()),
                                Column('created_at', DateTime(),
                                       nullable=False),
                                Column('updated_at', DateTime(),
                                       nullable=False),
                                Column('position', Integer()),
                                mysql_engine='InnoDB',
                                mysql_charset='utf8',
                                extend_existing=True)
    Index('ix_artifact_properties_artifact_id',
          artifact_properties.c.artifact_id)
    Index('ix_artifact_properties_name', artifact_properties.c.name)
    return artifact_properties


def define_artifact_blob_locations_table(meta):
    artifact_blob_locations = Table('artifact_blob_locations',
                                    meta,
                                    Column('id', String(36),
                                           primary_key=True,
                                           nullable=False),
                                    Column('blob_id', String(36),
                                           ForeignKey('artifact_blobs.id'),
                                           nullable=False),
                                    Column('value', Text(), nullable=False),
                                    Column('created_at', DateTime(),
                                           nullable=False),
                                    Column('updated_at', DateTime(),
                                           nullable=False),
                                    Column('position', Integer()),
                                    Column('status', String(36),
                                           nullable=True),
                                    mysql_engine='InnoDB',
                                    mysql_charset='utf8',
                                    extend_existing=True)
    Index('ix_artifact_blob_locations_blob_id',
          artifact_blob_locations.c.blob_id)

    return artifact_blob_locations


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = [define_artifacts_table(meta),
              define_artifact_tags_table(meta),
              define_artifact_properties_table(meta),
              define_artifact_blobs_table(meta),
              define_artifact_blob_locations_table(meta),
              define_artifact_dependencies_table(meta)]
    create_tables(tables)
