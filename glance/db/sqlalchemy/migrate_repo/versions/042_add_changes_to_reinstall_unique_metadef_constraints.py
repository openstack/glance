
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

import migrate
import sqlalchemy
from sqlalchemy import (func, Index, inspect, orm, String, Table, type_coerce)


# The _upgrade...get_duplicate() def's are separate functions to
# accommodate sqlite which locks the database against updates as long as
# db_recs is active.
# In addition, sqlite doesn't support the function 'concat' between
# Strings and Integers, so, the updating of records is also adjusted.
def _upgrade_metadef_namespaces_get_duplicates(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)
    metadef_namespaces = Table('metadef_namespaces', meta, autoload=True)

    session = orm.sessionmaker(bind=migrate_engine)()
    db_recs = (session.query(func.min(metadef_namespaces.c.id),
                             metadef_namespaces.c.namespace)
               .group_by(metadef_namespaces.c.namespace)
               .having(func.count(metadef_namespaces.c.namespace) > 1))
    dbrecs = []
    for row in db_recs:
        dbrecs.append({'id': row[0], 'namespace': row[1]})
    session.close()

    return dbrecs


def _upgrade_metadef_objects_get_duplicates(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)
    metadef_objects = Table('metadef_objects', meta, autoload=True)

    session = orm.sessionmaker(bind=migrate_engine)()
    db_recs = (session.query(func.min(metadef_objects.c.id),
                             metadef_objects.c.namespace_id,
                             metadef_objects.c.name)
               .group_by(metadef_objects.c.namespace_id,
                         metadef_objects.c.name)
               .having(func.count() > 1))
    dbrecs = []
    for row in db_recs:
        dbrecs.append({'id': row[0], 'namespace_id': row[1], 'name': row[2]})
    session.close()

    return dbrecs


def _upgrade_metadef_properties_get_duplicates(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)
    metadef_properties = Table('metadef_properties', meta, autoload=True)

    session = orm.sessionmaker(bind=migrate_engine)()
    db_recs = (session.query(func.min(metadef_properties.c.id),
                             metadef_properties.c.namespace_id,
                             metadef_properties.c.name)
               .group_by(metadef_properties.c.namespace_id,
                         metadef_properties.c.name)
               .having(func.count() > 1))
    dbrecs = []
    for row in db_recs:
        dbrecs.append({'id': row[0], 'namespace_id': row[1], 'name': row[2]})
    session.close()

    return dbrecs


def _upgrade_metadef_tags_get_duplicates(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)
    metadef_tags = Table('metadef_tags', meta, autoload=True)

    session = orm.sessionmaker(bind=migrate_engine)()
    db_recs = (session.query(func.min(metadef_tags.c.id),
                             metadef_tags.c.namespace_id,
                             metadef_tags.c.name)
               .group_by(metadef_tags.c.namespace_id,
                         metadef_tags.c.name)
               .having(func.count() > 1))
    dbrecs = []
    for row in db_recs:
        dbrecs.append({'id': row[0], 'namespace_id': row[1], 'name': row[2]})
    session.close()

    return dbrecs


def _upgrade_metadef_resource_types_get_duplicates(migrate_engine):
    meta = sqlalchemy.schema.MetaData(migrate_engine)
    metadef_resource_types = Table('metadef_resource_types', meta,
                                   autoload=True)

    session = orm.sessionmaker(bind=migrate_engine)()
    db_recs = (session.query(func.min(metadef_resource_types.c.id),
                             metadef_resource_types.c.name)
               .group_by(metadef_resource_types.c.name)
               .having(func.count(metadef_resource_types.c.name) > 1))
    dbrecs = []
    for row in db_recs:
        dbrecs.append({'id': row[0], 'name': row[1]})
    session.close()

    return dbrecs


def _upgrade_data(migrate_engine):
    # Rename duplicates to be unique.
    meta = sqlalchemy.schema.MetaData(migrate_engine)

    # ORM tables
    metadef_namespaces = Table('metadef_namespaces', meta, autoload=True)
    metadef_objects = Table('metadef_objects', meta, autoload=True)
    metadef_properties = Table('metadef_properties', meta, autoload=True)
    metadef_tags = Table('metadef_tags', meta, autoload=True)
    metadef_resource_types = Table('metadef_resource_types', meta,
                                   autoload=True)

    # Fix duplicate metadef_namespaces
    # Update the non-first record(s) with an unique namespace value
    dbrecs = _upgrade_metadef_namespaces_get_duplicates(migrate_engine)
    for row in dbrecs:
        s = (metadef_namespaces.update()
             .where(metadef_namespaces.c.id > row['id'])
             .where(metadef_namespaces.c.namespace == row['namespace'])
             )
        if migrate_engine.name == 'sqlite':
            s = (s.values(namespace=(row['namespace'] + '-DUPL-' +
                                     type_coerce(metadef_namespaces.c.id,
                                                 String)),
                          display_name=(row['namespace'] + '-DUPL-' +
                                        type_coerce(metadef_namespaces.c.id,
                                                    String))))
        else:
            s = s.values(namespace=func.concat(row['namespace'],
                                               '-DUPL-',
                                               metadef_namespaces.c.id),
                         display_name=func.concat(row['namespace'],
                                                  '-DUPL-',
                                                  metadef_namespaces.c.id))
        s.execute()

    # Fix duplicate metadef_objects
    dbrecs = _upgrade_metadef_objects_get_duplicates(migrate_engine)
    for row in dbrecs:
        s = (metadef_objects.update()
             .where(metadef_objects.c.id > row['id'])
             .where(metadef_objects.c.namespace_id == row['namespace_id'])
             .where(metadef_objects.c.name == str(row['name']))
             )
        if migrate_engine.name == 'sqlite':
            s = (s.values(name=(row['name'] + '-DUPL-'
                          + type_coerce(metadef_objects.c.id, String))))
        else:
            s = s.values(name=func.concat(row['name'], '-DUPL-',
                                          metadef_objects.c.id))
        s.execute()

    # Fix duplicate metadef_properties
    dbrecs = _upgrade_metadef_properties_get_duplicates(migrate_engine)
    for row in dbrecs:
        s = (metadef_properties.update()
             .where(metadef_properties.c.id > row['id'])
             .where(metadef_properties.c.namespace_id == row['namespace_id'])
             .where(metadef_properties.c.name == str(row['name']))
             )
        if migrate_engine.name == 'sqlite':
            s = (s.values(name=(row['name'] + '-DUPL-' +
                                type_coerce(metadef_properties.c.id, String)))
                 )
        else:
            s = s.values(name=func.concat(row['name'], '-DUPL-',
                                          metadef_properties.c.id))
        s.execute()

    # Fix duplicate metadef_tags
    dbrecs = _upgrade_metadef_tags_get_duplicates(migrate_engine)
    for row in dbrecs:
        s = (metadef_tags.update()
             .where(metadef_tags.c.id > row['id'])
             .where(metadef_tags.c.namespace_id == row['namespace_id'])
             .where(metadef_tags.c.name == str(row['name']))
             )
        if migrate_engine.name == 'sqlite':
            s = (s.values(name=(row['name'] + '-DUPL-' +
                                type_coerce(metadef_tags.c.id, String)))
                 )
        else:
            s = s.values(name=func.concat(row['name'], '-DUPL-',
                                          metadef_tags.c.id))
        s.execute()

    # Fix duplicate metadef_resource_types
    dbrecs = _upgrade_metadef_resource_types_get_duplicates(migrate_engine)
    for row in dbrecs:
        s = (metadef_resource_types.update()
             .where(metadef_resource_types.c.id > row['id'])
             .where(metadef_resource_types.c.name == str(row['name']))
             )
        if migrate_engine.name == 'sqlite':
            s = (s.values(name=(row['name'] + '-DUPL-' +
                                type_coerce(metadef_resource_types.c.id,
                                            String)))
                 )
        else:
            s = s.values(name=func.concat(row['name'], '-DUPL-',
                                          metadef_resource_types.c.id))
        s.execute()


def _update_sqlite_namespace_id_name_constraint(metadef, metadef_namespaces,
                                                new_constraint_name,
                                                new_fk_name):
    migrate.UniqueConstraint(
        metadef.c.namespace_id, metadef.c.name).drop()
    migrate.UniqueConstraint(
        metadef.c.namespace_id, metadef.c.name,
        name=new_constraint_name).create()
    migrate.ForeignKeyConstraint(
        [metadef.c.namespace_id],
        [metadef_namespaces.c.id],
        name=new_fk_name).create()


def _downgrade_sqlite_namespace_id_name_constraint(metadef,
                                                   metadef_namespaces,
                                                   constraint_name,
                                                   fk_name):
    migrate.UniqueConstraint(
        metadef.c.namespace_id,
        metadef.c.name,
        name=constraint_name).drop()
    migrate.UniqueConstraint(
        metadef.c.namespace_id,
        metadef.c.name).create()

    migrate.ForeignKeyConstraint(
        [metadef.c.namespace_id],
        [metadef_namespaces.c.id],
        name=fk_name).drop()
    migrate.ForeignKeyConstraint(
        [metadef.c.namespace_id],
        [metadef_namespaces.c.id]).create()


def _drop_unique_constraint_if_exists(inspector, table_name, metadef):
    name = _get_unique_constraint_name(inspector,
                                       table_name,
                                       ['namespace_id', 'name'])
    if name:
        migrate.UniqueConstraint(metadef.c.namespace_id,
                                 metadef.c.name,
                                 name=name).drop()


def _drop_index_with_fk_constraint(metadef, metadef_namespaces,
                                   index_name,
                                   fk_old_name, fk_new_name):

    fkc = migrate.ForeignKeyConstraint([metadef.c.namespace_id],
                                       [metadef_namespaces.c.id],
                                       name=fk_old_name)
    fkc.drop()

    if index_name:
        Index(index_name, metadef.c.namespace_id).drop()

    # Rename the fk for consistency across all db's
    fkc = migrate.ForeignKeyConstraint([metadef.c.namespace_id],
                                       [metadef_namespaces.c.id],
                                       name=fk_new_name)
    fkc.create()


def _downgrade_constraint_with_fk(metadef, metadef_namespaces,
                                  constraint_name,
                                  fk_curr_name, fk_next_name):

    fkc = migrate.ForeignKeyConstraint([metadef.c.namespace_id],
                                       [metadef_namespaces.c.id],
                                       name=fk_curr_name)
    fkc.drop()

    migrate.UniqueConstraint(metadef.c.namespace_id, metadef.c.name,
                             name=constraint_name).drop()

    fkc = migrate.ForeignKeyConstraint([metadef.c.namespace_id],
                                       [metadef_namespaces.c.id],
                                       name=fk_next_name)
    fkc.create()


def _get_unique_constraint_name(inspector, table_name, columns):
    constraints = inspector.get_unique_constraints(table_name)
    for constraint in constraints:
        if set(constraint['column_names']) == set(columns):
            return constraint['name']
    return None


def _get_fk_constraint_name(inspector, table_name, columns):
    constraints = inspector.get_foreign_keys(table_name)
    for constraint in constraints:
        if set(constraint['constrained_columns']) == set(columns):
            return constraint['name']
    return None


def upgrade(migrate_engine):

    _upgrade_data(migrate_engine)

    meta = sqlalchemy.MetaData()
    meta.bind = migrate_engine
    inspector = inspect(migrate_engine)

    # ORM tables
    metadef_namespaces = Table('metadef_namespaces', meta, autoload=True)
    metadef_objects = Table('metadef_objects', meta, autoload=True)
    metadef_properties = Table('metadef_properties', meta, autoload=True)
    metadef_tags = Table('metadef_tags', meta, autoload=True)
    metadef_ns_res_types = Table('metadef_namespace_resource_types',
                                 meta, autoload=True)
    metadef_resource_types = Table('metadef_resource_types', meta,
                                   autoload=True)

    # Drop the bad, non-unique indices.
    if migrate_engine.name == 'sqlite':
        # For sqlite:
        # Only after the unique constraints have been added should the indices
        # be dropped. If done the other way, sqlite complains during
        # constraint adding/dropping that the index does/does not exist.
        # Note: The _get_unique_constraint_name, _get_fk_constraint_name
        # return None for constraints that do in fact exist. Also,
        # get_index_names returns names, but, the names can not be used with
        # the Index(name, blah).drop() command, so, putting sqlite into
        # it's own section.

        # Objects
        _update_sqlite_namespace_id_name_constraint(
            metadef_objects, metadef_namespaces,
            'uq_metadef_objects_namespace_id_name',
            'metadef_objects_fk_1')

        # Properties
        _update_sqlite_namespace_id_name_constraint(
            metadef_properties, metadef_namespaces,
            'uq_metadef_properties_namespace_id_name',
            'metadef_properties_fk_1')

        # Tags
        _update_sqlite_namespace_id_name_constraint(
            metadef_tags, metadef_namespaces,
            'uq_metadef_tags_namespace_id_name',
            'metadef_tags_fk_1')

        # Namespaces
        migrate.UniqueConstraint(
            metadef_namespaces.c.namespace).drop()
        migrate.UniqueConstraint(
            metadef_namespaces.c.namespace,
            name='uq_metadef_namespaces_namespace').create()

        # ResourceTypes
        migrate.UniqueConstraint(
            metadef_resource_types.c.name).drop()
        migrate.UniqueConstraint(
            metadef_resource_types.c.name,
            name='uq_metadef_resource_types_name').create()

        # Now drop the bad indices
        Index('ix_metadef_objects_namespace_id',
              metadef_objects.c.namespace_id,
              metadef_objects.c.name).drop()
        Index('ix_metadef_properties_namespace_id',
              metadef_properties.c.namespace_id,
              metadef_properties.c.name).drop()
        Index('ix_metadef_tags_namespace_id',
              metadef_tags.c.namespace_id,
              metadef_tags.c.name).drop()
    else:
        # First drop the bad non-unique indices.
        # To do that (for mysql), must first drop foreign key constraints
        # BY NAME and then drop the bad indices.
        # Finally, re-create the foreign key constraints with a consistent
        # name.

        # DB2 still has unique constraints, but, they are badly named.
        # Drop them, they will be recreated at the final step.
        name = _get_unique_constraint_name(inspector, 'metadef_namespaces',
                                           ['namespace'])
        if name:
            migrate.UniqueConstraint(metadef_namespaces.c.namespace,
                                     name=name).drop()
        _drop_unique_constraint_if_exists(inspector, 'metadef_objects',
                                          metadef_objects)
        _drop_unique_constraint_if_exists(inspector, 'metadef_properties',
                                          metadef_properties)
        _drop_unique_constraint_if_exists(inspector, 'metadef_tags',
                                          metadef_tags)
        name = _get_unique_constraint_name(inspector, 'metadef_resource_types',
                                           ['name'])
        if name:
            migrate.UniqueConstraint(metadef_resource_types.c.name,
                                     name=name).drop()

        # Objects
        _drop_index_with_fk_constraint(
            metadef_objects, metadef_namespaces,
            'ix_metadef_objects_namespace_id',
            _get_fk_constraint_name(
                inspector, 'metadef_objects', ['namespace_id']),
            'metadef_objects_fk_1')

        # Properties
        _drop_index_with_fk_constraint(
            metadef_properties, metadef_namespaces,
            'ix_metadef_properties_namespace_id',
            _get_fk_constraint_name(
                inspector, 'metadef_properties', ['namespace_id']),
            'metadef_properties_fk_1')

        # Tags
        _drop_index_with_fk_constraint(
            metadef_tags, metadef_namespaces,
            'ix_metadef_tags_namespace_id',
            _get_fk_constraint_name(
                inspector, 'metadef_tags', ['namespace_id']),
            'metadef_tags_fk_1')

    # Drop Others without fk constraints.
    Index('ix_metadef_namespaces_namespace',
          metadef_namespaces.c.namespace).drop()

    # The next two don't exist in ibm_db_sa, but, drop them everywhere else.
    if migrate_engine.name != 'ibm_db_sa':
        Index('ix_metadef_resource_types_name',
              metadef_resource_types.c.name).drop()
        # Not needed due to primary key on same columns
        Index('ix_metadef_ns_res_types_res_type_id_ns_id',
              metadef_ns_res_types.c.resource_type_id,
              metadef_ns_res_types.c.namespace_id).drop()

    # Now, add back the dropped indexes as unique constraints
    if migrate_engine.name != 'sqlite':
        # Namespaces
        migrate.UniqueConstraint(
            metadef_namespaces.c.namespace,
            name='uq_metadef_namespaces_namespace').create()

        # Objects
        migrate.UniqueConstraint(
            metadef_objects.c.namespace_id,
            metadef_objects.c.name,
            name='uq_metadef_objects_namespace_id_name').create()

        # Properties
        migrate.UniqueConstraint(
            metadef_properties.c.namespace_id,
            metadef_properties.c.name,
            name='uq_metadef_properties_namespace_id_name').create()

        # Tags
        migrate.UniqueConstraint(
            metadef_tags.c.namespace_id,
            metadef_tags.c.name,
            name='uq_metadef_tags_namespace_id_name').create()

        # Resource Types
        migrate.UniqueConstraint(
            metadef_resource_types.c.name,
            name='uq_metadef_resource_types_name').create()


def downgrade(migrate_engine):
    meta = sqlalchemy.MetaData()
    meta.bind = migrate_engine

    # ORM tables
    metadef_namespaces = Table('metadef_namespaces', meta, autoload=True)
    metadef_objects = Table('metadef_objects', meta, autoload=True)
    metadef_properties = Table('metadef_properties', meta, autoload=True)
    metadef_tags = Table('metadef_tags', meta, autoload=True)
    metadef_resource_types = Table('metadef_resource_types', meta,
                                   autoload=True)
    metadef_ns_res_types = Table('metadef_namespace_resource_types',
                                 meta, autoload=True)

    # Drop the unique constraints
    if migrate_engine.name == 'sqlite':
        # Objects
        _downgrade_sqlite_namespace_id_name_constraint(
            metadef_objects, metadef_namespaces,
            'uq_metadef_objects_namespace_id_name',
            'metadef_objects_fk_1')

        # Properties
        _downgrade_sqlite_namespace_id_name_constraint(
            metadef_properties, metadef_namespaces,
            'uq_metadef_properties_namespace_id_name',
            'metadef_properties_fk_1')

        # Tags
        _downgrade_sqlite_namespace_id_name_constraint(
            metadef_tags, metadef_namespaces,
            'uq_metadef_tags_namespace_id_name',
            'metadef_tags_fk_1')

        # Namespaces
        migrate.UniqueConstraint(
            metadef_namespaces.c.namespace,
            name='uq_metadef_namespaces_namespace').drop()
        migrate.UniqueConstraint(
            metadef_namespaces.c.namespace).create()

        # ResourceTypes
        migrate.UniqueConstraint(
            metadef_resource_types.c.name,
            name='uq_metadef_resource_types_name').drop()
        migrate.UniqueConstraint(
            metadef_resource_types.c.name).create()
    else:
        # For mysql, must drop foreign key constraints before dropping the
        # unique constraint. So drop the fkc, then drop the constraints,
        # then recreate the fkc.

        # Objects
        _downgrade_constraint_with_fk(
            metadef_objects, metadef_namespaces,
            'uq_metadef_objects_namespace_id_name',
            'metadef_objects_fk_1', None)

        # Properties
        _downgrade_constraint_with_fk(
            metadef_properties, metadef_namespaces,
            'uq_metadef_properties_namespace_id_name',
            'metadef_properties_fk_1', None)

        # Tags
        _downgrade_constraint_with_fk(
            metadef_tags, metadef_namespaces,
            'uq_metadef_tags_namespace_id_name',
            'metadef_tags_fk_1', 'metadef_tags_namespace_id_fkey')

        # Namespaces
        migrate.UniqueConstraint(
            metadef_namespaces.c.namespace,
            name='uq_metadef_namespaces_namespace').drop()

        # Resource_types
        migrate.UniqueConstraint(
            metadef_resource_types.c.name,
            name='uq_metadef_resource_types_name').drop()

    # Create dropped unique constraints as bad, non-unique indexes
    Index('ix_metadef_objects_namespace_id',
          metadef_objects.c.namespace_id).create()
    Index('ix_metadef_properties_namespace_id',
          metadef_properties.c.namespace_id).create()

    # These need to be done before the metadef_tags and metadef_namespaces
    # unique constraints are created to avoid 'tuple out of range' errors
    # in db2.
    Index('ix_metadef_tags_namespace_id',
          metadef_tags.c.namespace_id,
          metadef_tags.c.name).create()
    Index('ix_metadef_namespaces_namespace',
          metadef_namespaces.c.namespace).create()

    # Create these everywhere, except for db2
    if migrate_engine.name != 'ibm_db_sa':
        Index('ix_metadef_resource_types_name',
              metadef_resource_types.c.name).create()
        Index('ix_metadef_ns_res_types_res_type_id_ns_id',
              metadef_ns_res_types.c.resource_type_id,
              metadef_ns_res_types.c.namespace_id).create()
    else:
        # Recreate the badly named unique constraints in db2
        migrate.UniqueConstraint(
            metadef_namespaces.c.namespace,
            name='ix_namespaces_namespace').create()
        migrate.UniqueConstraint(
            metadef_objects.c.namespace_id,
            metadef_objects.c.name,
            name='ix_objects_namespace_id_name').create()
        migrate.UniqueConstraint(
            metadef_properties.c.namespace_id,
            metadef_properties.c.name,
            name='ix_metadef_properties_namespace_id_name').create()
        migrate.UniqueConstraint(
            metadef_tags.c.namespace_id,
            metadef_tags.c.name).create()
        migrate.UniqueConstraint(
            metadef_resource_types.c.name,
            name='ix_metadef_resource_types_name').create()
