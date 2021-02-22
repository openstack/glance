# Copyright 2021 Red Hat, Inc.
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

import os

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import uuidutils

from glance.common import exception
from glance.common import store_utils
from glance import context
from glance.i18n import _LE

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def staging_store_path():
    """Return the local path to the staging store.

    :raises: GlanceException if staging store is not configured to be
             a file:// URI
    """
    if CONF.enabled_backends:
        separator, staging_dir = store_utils.get_dir_separator()
    else:
        staging_dir = CONF.node_staging_uri
    expected_prefix = 'file://'
    if not staging_dir.startswith(expected_prefix):
        raise exception.GlanceException(
            'Unexpected scheme in staging store; '
            'unable to scan for residue')
    return staging_dir[len(expected_prefix):]


class StagingStoreCleaner:
    def __init__(self, db):
        self.db = db
        self.context = context.get_admin_context()

    @staticmethod
    def get_image_id(filename):
        if '.' in filename:
            filename, ext = filename.split('.', 1)
        if uuidutils.is_uuid_like(filename):
            return filename

    def is_valid_image(self, image_id):
        try:
            image = self.db.image_get(self.context, image_id)
            # FIXME(danms): Maybe check that it's not deleted or
            # something else like state, size, etc
            return not image['deleted']
        except exception.ImageNotFound:
            return False

    @staticmethod
    def delete_file(path):
        try:
            os.remove(path)
        except FileNotFoundError:
            # NOTE(danms): We must have raced with something else, so this
            # is not a problem
            pass
        except Exception as e:
            LOG.error(_LE('Failed to delete stale staging '
                          'path %(path)r: %(err)s'),
                      {'path': path, 'err': str(e)})
            return False
        return True

    def clean_orphaned_staging_residue(self):
        try:
            files = os.listdir(staging_store_path())
        except FileNotFoundError:
            # NOTE(danms): If we cannot list the staging dir, there is
            # clearly nothing left from a previous run, so nothing to
            # clean up.
            files = []
        if not files:
            return

        LOG.debug('Found %i files in staging directory for potential cleanup',
                  len(files))
        cleaned = ignored = error = 0
        for filename in files:
            image_id = self.get_image_id(filename)
            if not image_id:
                # NOTE(danms): We should probably either have a config option
                # that decides what to do here (i.e. reap or ignore), or decide
                # that this is not okay and just nuke anything we find.
                LOG.debug('Staging directory contains unexpected non-image '
                          'file %r; ignoring',
                          filename)
                ignored += 1
                continue
            if self.is_valid_image(image_id):
                # NOTE(danms): We found a non-deleted image for this
                # file, so leave it in place.
                ignored += 1
                continue
            path = os.path.join(staging_store_path(), filename)
            LOG.debug('Stale staging residue found for image '
                      '%(uuid)s: %(file)r; deleting now.',
                      {'uuid': image_id, 'file': path})
            if self.delete_file(path):
                cleaned += 1
            else:
                error += 1

        LOG.debug('Cleaned %(cleaned)i stale staging files, '
                  '%(ignored)i ignored (%(error)i errors)',
                  {'cleaned': cleaned, 'ignored': ignored, 'error': error})
