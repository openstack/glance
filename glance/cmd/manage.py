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

from __future__ import print_function

# FIXME(sirp): When we have glance-admin we can consider merging this into it
# Perhaps for consistency with Nova, we would then rename glance-admin ->
# glance-manage (or the other way around)

import os
import sys

# If ../glance/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)

from oslo_config import cfg
from oslo_db.sqlalchemy import migration
from oslo_log import log as logging
from oslo_utils import encodeutils
import six

from glance.common import config
from glance.common import exception
from glance.db import migration as db_migration
from glance.db.sqlalchemy import api as db_api
from glance.db.sqlalchemy import metadata
from glance import i18n


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
_ = i18n._


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
        print(migration.db_version(db_api.get_engine(),
                                   db_migration.MIGRATE_REPO_PATH,
                                   db_migration.INIT_VERSION))

    @args('--version', metavar='<version>', help='Database version')
    def upgrade(self, version=None):
        """Upgrade the database's migration level"""
        migration.db_sync(db_api.get_engine(),
                          db_migration.MIGRATE_REPO_PATH,
                          version)

    @args('--version', metavar='<version>', help='Database version')
    def downgrade(self, version=None):
        """Downgrade the database's migration level"""
        migration.db_sync(db_api.get_engine(),
                          db_migration.MIGRATE_REPO_PATH,
                          version)

    @args('--version', metavar='<version>', help='Database version')
    def version_control(self, version=None):
        """Place a database under migration control"""
        migration.db_version_control(db_api.get_engine(),
                                     db_migration.MIGRATE_REPO_PATH,
                                     version)

    @args('--version', metavar='<version>', help='Database version')
    @args('--current_version', metavar='<version>',
          help='Current Database version')
    def sync(self, version=None, current_version=None):
        """
        Place a database under migration control and upgrade/downgrade it,
        creating first if necessary.
        """
        if current_version not in (None, 'None'):
            migration.db_version_control(db_api.get_engine(),
                                         db_migration.MIGRATE_REPO_PATH,
                                         version=current_version)
        migration.db_sync(db_api.get_engine(),
                          db_migration.MIGRATE_REPO_PATH,
                          version)

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


class DbLegacyCommands(object):
    """Class for managing the db using legacy commands"""

    def __init__(self, command_object):
        self.command_object = command_object

    def version(self):
        self.command_object.version()

    def upgrade(self, version=None):
        self.command_object.upgrade(CONF.command.version)

    def downgrade(self, version=None):
        self.command_object.downgrade(CONF.command.version)

    def version_control(self, version=None):
        self.command_object.version_control(CONF.command.version)

    def sync(self, version=None, current_version=None):
        self.command_object.sync(CONF.command.version,
                                 CONF.command.current_version)

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

    parser = subparsers.add_parser('db_downgrade')
    parser.set_defaults(action_fn=legacy_command_object.downgrade)
    parser.add_argument('version')
    parser.set_defaults(action='db_downgrade')

    parser = subparsers.add_parser('db_version_control')
    parser.set_defaults(action_fn=legacy_command_object.version_control)
    parser.add_argument('version', nargs='?')
    parser.set_defaults(action='db_version_control')

    parser = subparsers.add_parser('db_sync')
    parser.set_defaults(action_fn=legacy_command_object.sync)
    parser.add_argument('version', nargs='?')
    parser.add_argument('current_version', nargs='?')
    parser.set_defaults(action='db_sync')

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
        cfg_files = cfg.find_config_files(project='glance',
                                          prog='glance-registry')
        cfg_files.extend(cfg.find_config_files(project='glance',
                                               prog='glance-api'))
        cfg_files.extend(cfg.find_config_files(project='glance',
                                               prog='glance-manage'))
        config.parse_args(default_config_files=cfg_files)
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
                if isinstance(v, six.string_types):
                    v = encodeutils.safe_decode(v)
                func_kwargs[k] = v
            func_args = [encodeutils.safe_decode(arg)
                         for arg in CONF.command.action_args]
            return CONF.command.action_fn(*func_args, **func_kwargs)
    except exception.GlanceException as e:
        sys.exit("ERROR: %s" % encodeutils.exception_to_unicode(e))


if __name__ == '__main__':
    main()
