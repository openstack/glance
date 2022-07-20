#!/usr/bin/env python

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 OpenStack Foundation
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
Glance Management Utility
"""

# FIXME(sirp): When we have glance-admin we can consider merging this into it
# Perhaps for consistency with Nova, we would then rename glance-admin ->
# glance-manage (or the other way around)

import os
import sys
import time

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)

from alembic import command as alembic_command

from oslo_config import cfg
from oslo_db import exception as db_exc
from oslo_log import log as logging
from oslo_utils import encodeutils

from glance.common import config
from glance.common import exception
from glance import context
from glance.db import migration as db_migration
from glance.db.sqlalchemy import alembic_migrations
from glance.db.sqlalchemy.alembic_migrations import data_migrations
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import metadata
from glance.i18n import _


CONF = cfg.CONF
USE_TRIGGERS = True


# Decorators for actions
def args(*args, **kwargs):
    def _decorator(func):
        func.__dict__.setdefault('args', []).insert(0, (args, kwargs))
        return func
    return _decorator


class DbCommands(object):
    """Class for managing the db"""

    def __init__(self):
        pass

    def version(self):
        """Print database's current migration level"""
        current_heads = alembic_migrations.get_current_alembic_heads()
        if current_heads:
            # Migrations are managed by alembic
            for head in current_heads:
                print(head)
        else:
            # Migrations are managed by legacy versioning scheme
            print(_('Database is either not under migration control or under '
                    'legacy migration control, please run '
                    '"glance-manage db sync" to place the database under '
                    'alembic migration control.'))

    def check(self):
        """Report any pending database upgrades.

        An exit code of 3 indicates db expand is needed, see stdout output.
        An exit code of 4 indicates db migrate is needed, see stdout output.
        An exit code of 5 indicates db contract is needed, see stdout output.
        """
        engine = db_api.get_engine()
        self._validate_engine(engine)

        curr_heads = alembic_migrations.get_current_alembic_heads()

        expand_heads = alembic_migrations.get_alembic_branch_head(
            db_migration.EXPAND_BRANCH)
        contract_heads = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        if (contract_heads in curr_heads):
            print(_('Database is up to date. No upgrades needed.'))
            sys.exit()
        elif ((not expand_heads) or (expand_heads not in curr_heads)):
            print(_('Your database is not up to date. '
                    'Your first step is to run `glance-manage db expand`.'))
            sys.exit(3)
        elif data_migrations.has_pending_migrations(db_api.get_engine()):
            print(_('Your database is not up to date. '
                    'Your next step is to run `glance-manage db migrate`.'))
            sys.exit(4)
        elif ((not contract_heads) or (contract_heads not in curr_heads)):
            print(_('Your database is not up to date. '
                    'Your next step is to run `glance-manage db contract`.'))
            sys.exit(5)

    @args('--version', metavar='<version>', help='Database version')
    def upgrade(self, version='heads'):
        """Upgrade the database's migration level"""
        self._sync(version)

    @args('--version', metavar='<version>', help='Database version')
    def version_control(self, version=db_migration.ALEMBIC_INIT_VERSION):
        """Place a database under migration control"""

        if version is None:
            version = db_migration.ALEMBIC_INIT_VERSION

        a_config = alembic_migrations.get_alembic_config()
        alembic_command.stamp(a_config, version)
        print(_("Placed database under migration control at "
                "revision:"), version)

    @args('--version', metavar='<version>', help='Database version')
    def sync(self, version=None):
        """Perform a complete (offline) database migration"""
        global USE_TRIGGERS

        # This flags let's us bypass trigger setup & teardown for non-rolling
        # upgrades. We set this as a global variable immediately before handing
        # off to alembic, because we can't pass arguments directly to
        # migrations that depend on it.
        USE_TRIGGERS = False

        curr_heads = alembic_migrations.get_current_alembic_heads()
        contract = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        if contract in curr_heads:
            print(_('Database is up to date. No migrations needed.'))
            sys.exit()

        try:
            # NOTE(abhishekk): db_sync should not be used for online
            # migrations.
            self.expand(online_migration=False)
            self.migrate(online_migration=False)
            self.contract(online_migration=False)
            print(_('Database is synced successfully.'))
        except exception.GlanceException as e:
            sys.exit(_('Failed to sync database: ERROR: %s') % e)

    def _sync(self, version):
        """
        Place an existing database under migration control and upgrade it.
        """

        a_config = alembic_migrations.get_alembic_config()
        alembic_command.upgrade(a_config, version)
        heads = alembic_migrations.get_current_alembic_heads()
        if heads is None:
            raise exception.GlanceException("Database sync failed")
        revs = ", ".join(heads)
        if version == 'heads':
            print(_("Upgraded database, current revision(s):"), revs)
        else:
            print(_('Upgraded database to: %(v)s, current revision(s): %(r)s')
                  % {'v': version, 'r': revs})

    def _validate_engine(self, engine):
        """Check engine is valid or not.

        MySql is only supported for online upgrade.
        Adding sqlite as engine to support existing functional test cases.

        :param engine: database engine name
        """
        if engine.engine.name not in ['mysql', 'sqlite']:
            sys.exit(_('Rolling upgrades are currently supported only for '
                       'MySQL and Sqlite'))

    def expand(self, online_migration=True):
        """Run the expansion phase of a database migration."""
        if online_migration:
            self._validate_engine(db_api.get_engine())

        curr_heads = alembic_migrations.get_current_alembic_heads()
        expand_head = alembic_migrations.get_alembic_branch_head(
            db_migration.EXPAND_BRANCH)
        contract_head = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        if not expand_head:
            sys.exit(_('Database expansion failed. Couldn\'t find head '
                       'revision of expand branch.'))
        elif (contract_head in curr_heads):
            print(_('Database is up to date. No migrations needed.'))
            sys.exit()

        if expand_head not in curr_heads:
            self._sync(version=expand_head)

            curr_heads = alembic_migrations.get_current_alembic_heads()
            if expand_head not in curr_heads:
                sys.exit(_('Database expansion failed. Database expansion '
                           'should have brought the database version up to '
                           '"%(e_rev)s" revision. But, current revisions are'
                           ': %(curr_revs)s ') % {'e_rev': expand_head,
                                                  'curr_revs': curr_heads})
        else:
            print(_('Database expansion is up to date. No expansion needed.'))

    def contract(self, online_migration=True):
        """Run the contraction phase of a database migration."""
        if online_migration:
            self._validate_engine(db_api.get_engine())

        curr_heads = alembic_migrations.get_current_alembic_heads()
        contract_head = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        if not contract_head:
            sys.exit(_('Database contraction failed. Couldn\'t find head '
                       'revision of contract branch.'))
        elif (contract_head in curr_heads):
            print(_('Database is up to date. No migrations needed.'))
            sys.exit()

        expand_head = alembic_migrations.get_alembic_branch_head(
            db_migration.EXPAND_BRANCH)
        if expand_head not in curr_heads:
            sys.exit(_('Database contraction did not run. Database '
                       'contraction cannot be run before database expansion. '
                       'Run database expansion first using '
                       '"glance-manage db expand"'))

        if data_migrations.has_pending_migrations(db_api.get_engine()):
            sys.exit(_('Database contraction did not run. Database '
                       'contraction cannot be run before data migration is '
                       'complete. Run data migration using "glance-manage db '
                       'migrate".'))

        self._sync(version=contract_head)

        curr_heads = alembic_migrations.get_current_alembic_heads()
        if contract_head not in curr_heads:
            sys.exit(_('Database contraction failed. Database contraction '
                       'should have brought the database version up to '
                       '"%(e_rev)s" revision. But, current revisions are: '
                       '%(curr_revs)s ') % {'e_rev': expand_head,
                                            'curr_revs': curr_heads})

    def migrate(self, online_migration=True):
        """Run the data migration phase of a database migration."""
        if online_migration:
            self._validate_engine(db_api.get_engine())

        curr_heads = alembic_migrations.get_current_alembic_heads()
        contract_head = alembic_migrations.get_alembic_branch_head(
            db_migration.CONTRACT_BRANCH)

        if (contract_head in curr_heads):
            print(_('Database is up to date. No migrations needed.'))
            sys.exit()

        expand_head = alembic_migrations.get_alembic_branch_head(
            db_migration.EXPAND_BRANCH)
        if expand_head not in curr_heads:
            sys.exit(_('Data migration did not run. Data migration cannot be '
                       'run before database expansion. Run database '
                       'expansion first using "glance-manage db expand"'))

        if data_migrations.has_pending_migrations(db_api.get_engine()):
            rows_migrated = data_migrations.migrate(db_api.get_engine())
            print(_('Migrated %s rows') % rows_migrated)
        else:
            print(_('Database migration is up to date. No migration needed.'))

    @args('--path', metavar='<path>', help='Path to the directory or file '
                                           'where json metadata is stored')
    @args('--merge', action='store_true',
          help='Merge files with data that is in the database. By default it '
               'prefers existing data over new. This logic can be changed by '
               'combining --merge option with one of these two options: '
               '--prefer_new or --overwrite.')
    @args('--prefer_new', action='store_true',
          help='Prefer new metadata over existing. Existing metadata '
               'might be overwritten. Needs to be combined with --merge '
               'option.')
    @args('--overwrite', action='store_true',
          help='Drop and rewrite metadata. Needs to be combined with --merge '
               'option')
    def load_metadefs(self, path=None, merge=False,
                      prefer_new=False, overwrite=False):
        """Load metadefinition json files to database"""
        metadata.db_load_metadefs(db_api.get_engine(), path, merge,
                                  prefer_new, overwrite)

    def unload_metadefs(self):
        """Unload metadefinitions from database"""
        metadata.db_unload_metadefs(db_api.get_engine())

    @args('--path', metavar='<path>', help='Path to the directory where '
                                           'json metadata files should be '
                                           'saved.')
    def export_metadefs(self, path=None):
        """Export metadefinitions data from database to files"""
        metadata.db_export_metadefs(db_api.get_engine(),
                                    path)

    def _purge(self, age_in_days, max_rows, purge_images_only=False):
        try:
            age_in_days = int(age_in_days)
        except ValueError:
            sys.exit(_("Invalid int value for age_in_days: "
                       "%(age_in_days)s") % {'age_in_days': age_in_days})
        try:
            max_rows = int(max_rows)
        except ValueError:
            sys.exit(_("Invalid int value for max_rows: "
                       "%(max_rows)s") % {'max_rows': max_rows})
        if age_in_days < 0:
            sys.exit(_("Must supply a non-negative value for age."))
        if age_in_days >= (int(time.time()) / 86400):
            sys.exit(_("Maximal age is count of days since epoch."))
        if max_rows < -1:
            sys.exit(_("Minimal rows limit is -1."))
        ctx = context.get_admin_context(show_deleted=True)
        try:
            if purge_images_only:
                db_api.purge_deleted_rows_from_images(ctx, age_in_days,
                                                      max_rows)
            else:
                db_api.purge_deleted_rows(ctx, age_in_days, max_rows)
        except exception.Invalid as exc:
            sys.exit(exc.msg)
        except db_exc.DBReferenceError:
            sys.exit(_("Purge command failed, check glance-manage"
                       " logs for more details."))

    @args('--age_in_days', type=int,
          help='Purge deleted rows older than age in days')
    @args('--max_rows', type=int,
          help='Limit number of records to delete. All deleted rows will be '
               'purged if equals -1.')
    def purge(self, age_in_days=30, max_rows=100):
        """Purge deleted rows older than a given age from glance tables."""
        self._purge(age_in_days, max_rows)

    @args('--age_in_days', type=int,
          help='Purge deleted rows older than age in days')
    @args('--max_rows', type=int,
          help='Limit number of records to delete. All deleted rows will be '
               'purged if equals -1.')
    def purge_images_table(self, age_in_days=180, max_rows=100):
        """Purge deleted rows older than a given age from images table."""
        self._purge(age_in_days, max_rows, purge_images_only=True)


class DbLegacyCommands(object):
    """Class for managing the db using legacy commands"""

    def __init__(self, command_object):
        self.command_object = command_object

    def version(self):
        self.command_object.version()

    def upgrade(self, version='heads'):
        self.command_object.upgrade(CONF.command.version)

    def version_control(self, version=db_migration.ALEMBIC_INIT_VERSION):
        self.command_object.version_control(CONF.command.version)

    def sync(self, version=None):
        self.command_object.sync(CONF.command.version)

    def expand(self):
        self.command_object.expand()

    def contract(self):
        self.command_object.contract()

    def migrate(self):
        self.command_object.migrate()

    def check(self):
        self.command_object.check()

    def load_metadefs(self, path=None, merge=False,
                      prefer_new=False, overwrite=False):
        self.command_object.load_metadefs(CONF.command.path,
                                          CONF.command.merge,
                                          CONF.command.prefer_new,
                                          CONF.command.overwrite)

    def unload_metadefs(self):
        self.command_object.unload_metadefs()

    def export_metadefs(self, path=None):
        self.command_object.export_metadefs(CONF.command.path)


def add_legacy_command_parsers(command_object, subparsers):

    legacy_command_object = DbLegacyCommands(command_object)

    parser = subparsers.add_parser('db_version')
    parser.set_defaults(action_fn=legacy_command_object.version)
    parser.set_defaults(action='db_version')

    parser = subparsers.add_parser('db_upgrade')
    parser.set_defaults(action_fn=legacy_command_object.upgrade)
    parser.add_argument('version', nargs='?')
    parser.set_defaults(action='db_upgrade')

    parser = subparsers.add_parser('db_version_control')
    parser.set_defaults(action_fn=legacy_command_object.version_control)
    parser.add_argument('version', nargs='?')
    parser.set_defaults(action='db_version_control')

    parser = subparsers.add_parser('db_sync')
    parser.set_defaults(action_fn=legacy_command_object.sync)
    parser.add_argument('version', nargs='?')
    parser.set_defaults(action='db_sync')

    parser = subparsers.add_parser('db_expand')
    parser.set_defaults(action_fn=legacy_command_object.expand)
    parser.set_defaults(action='db_expand')

    parser = subparsers.add_parser('db_contract')
    parser.set_defaults(action_fn=legacy_command_object.contract)
    parser.set_defaults(action='db_contract')

    parser = subparsers.add_parser('db_migrate')
    parser.set_defaults(action_fn=legacy_command_object.migrate)
    parser.set_defaults(action='db_migrate')

    parser = subparsers.add_parser('db_check')
    parser.set_defaults(action_fn=legacy_command_object.check)
    parser.set_defaults(action='db_check')

    parser = subparsers.add_parser('db_load_metadefs')
    parser.set_defaults(action_fn=legacy_command_object.load_metadefs)
    parser.add_argument('path', nargs='?')
    parser.add_argument('merge', nargs='?')
    parser.add_argument('prefer_new', nargs='?')
    parser.add_argument('overwrite', nargs='?')
    parser.set_defaults(action='db_load_metadefs')

    parser = subparsers.add_parser('db_unload_metadefs')
    parser.set_defaults(action_fn=legacy_command_object.unload_metadefs)
    parser.set_defaults(action='db_unload_metadefs')

    parser = subparsers.add_parser('db_export_metadefs')
    parser.set_defaults(action_fn=legacy_command_object.export_metadefs)
    parser.add_argument('path', nargs='?')
    parser.set_defaults(action='db_export_metadefs')


def add_command_parsers(subparsers):
    command_object = DbCommands()

    parser = subparsers.add_parser('db')
    parser.set_defaults(command_object=command_object)

    category_subparsers = parser.add_subparsers(dest='action')

    for (action, action_fn) in methods_of(command_object):
        parser = category_subparsers.add_parser(action)

        action_kwargs = []
        for args, kwargs in getattr(action_fn, 'args', []):
            # FIXME(basha): hack to assume dest is the arg name without
            # the leading hyphens if no dest is supplied
            kwargs.setdefault('dest', args[0][2:])
            if kwargs['dest'].startswith('action_kwarg_'):
                action_kwargs.append(
                    kwargs['dest'][len('action_kwarg_'):])
            else:
                action_kwargs.append(kwargs['dest'])
                kwargs['dest'] = 'action_kwarg_' + kwargs['dest']

            parser.add_argument(*args, **kwargs)

        parser.set_defaults(action_fn=action_fn)
        parser.set_defaults(action_kwargs=action_kwargs)

        parser.add_argument('action_args', nargs='*')

    add_legacy_command_parsers(command_object, subparsers)


command_opt = cfg.SubCommandOpt('command',
                                title='Commands',
                                help='Available commands',
                                handler=add_command_parsers)


CATEGORIES = {
    'db': DbCommands,
}


def methods_of(obj):
    """Get all callable methods of an object that don't start with underscore

    returns a list of tuples of the form (method_name, method)
    """
    result = []
    for i in dir(obj):
        if callable(getattr(obj, i)) and not i.startswith('_'):
            result.append((i, getattr(obj, i)))
    return result


def main():
    CONF.register_cli_opt(command_opt)
    if len(sys.argv) < 2:
        script_name = sys.argv[0]
        print("%s category action [<args>]" % script_name)
        print(_("Available categories:"))
        for category in CATEGORIES:
            print(_("\t%s") % category)
        sys.exit(2)

    try:
        logging.register_options(CONF)
        CONF.set_default(name='use_stderr', default=True)
        cfg_files = cfg.find_config_files(project='glance',
                                          prog='glance-api')
        cfg_files.extend(cfg.find_config_files(project='glance',
                                               prog='glance-manage'))
        config.parse_args(default_config_files=cfg_files)
        config.set_config_defaults()
        logging.setup(CONF, 'glance')
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)

    try:
        if CONF.command.action.startswith('db'):
            return CONF.command.action_fn()
        else:
            func_kwargs = {}
            for k in CONF.command.action_kwargs:
                v = getattr(CONF.command, 'action_kwarg_' + k)
                if v is None:
                    continue
                if isinstance(v, str):
                    v = encodeutils.safe_decode(v)
                func_kwargs[k] = v
            func_args = [encodeutils.safe_decode(arg)
                         for arg in CONF.command.action_args]
            return CONF.command.action_fn(*func_args, **func_kwargs)
    except exception.GlanceException as e:
        sys.exit("ERROR: %s" % encodeutils.exception_to_unicode(e))


if __name__ == '__main__':
    main()
