# Copyright 2024 RedHat Inc.
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
import hashlib

import glance_store as store
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import secretutils
from taskflow.patterns import linear_flow as lf
from taskflow import retry
from taskflow import task

import glance.async_.flows.api_image_import as image_import
from glance.common import exception
from glance.common import store_utils
from glance.i18n import _, _LW


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class _HashCalculationFailed(exception.GlanceException):

    def __init__(self, message):
        super(_HashCalculationFailed, self).__init__(message)


class _InvalidLocation(exception.GlanceException):

    def __init__(self, message):
        super(_InvalidLocation, self).__init__(message)


class _CalculateHash(task.Task):

    def __init__(self, task_id, task_type, image_repo, image_id,
                 hashing_algo, status=None):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        self.hashing_algo = hashing_algo
        self.image_status = status
        super(_CalculateHash, self).__init__(
            name='%s-CalculateHash-%s' % (task_type, task_id))

    def _calculate_hash(self, image):
        current_os_hash_value = hashlib.new(self.hashing_algo)
        current_checksum = secretutils.md5(usedforsecurity=False)
        for chunk in image.get_data():
            if chunk is None:
                break
            current_checksum.update(chunk)
            current_os_hash_value.update(chunk)
        image.checksum = current_checksum.hexdigest()
        image.os_hash_value = current_os_hash_value.hexdigest()

    def _set_checksum_and_hash(self, image):
        retries = 0
        while retries <= CONF.http_retries and image.os_hash_value is None:
            retries += 1
            try:
                self._calculate_hash(image)
                self.image_repo.save(image)
            except IOError as e:
                LOG.debug('[%i/%i] Hash calculation failed due to %s',
                          retries, CONF.http_retries,
                          encodeutils.exception_to_unicode(e))
                if retries == CONF.http_retries:
                    if image.status != 'active':
                        # NOTE(pdeore): The image location add operation
                        # should succeed so this exception should be raised
                        # only when image status is not active.
                        msg = (_('Hash calculation failed for image %s '
                                 'data') % self.image_id)
                        raise _HashCalculationFailed(msg)
                    else:
                        msg = (_LW("Hash calculation failed for image %s "
                                   "data") % self.image_id)
                        LOG.warning(msg)
            except store.exceptions.NotFound:
                # NOTE(pdeore): This can happen if image delete attempted
                # when hash calculation is in progress, which deletes the
                # image data from backend(specially rbd) but image remains
                # in 'active' state.
                # see: https://bugs.launchpad.net/glance/+bug/2045769
                # Once this ceph side issue is fixed, we'll keep only the
                # warning message here and will remove the deletion part
                # which is a temporary workaround.
                LOG.debug(_('Failed to calculate checksum of %(image_id)s '
                            'as image data has been deleted from the '
                            'backend'), {'image_id': self.image_id})
                image.delete()
                self.image_repo.remove(image)
                break

    def execute(self):
        image = self.image_repo.get(self.image_id)
        if image.status == 'queued':
            image.status = self.image_status
        image.os_hash_algo = self.hashing_algo
        self.image_repo.save(image)
        self._set_checksum_and_hash(image)

    def revert(self, result, **kwargs):
        """Set os_hash_algo to None when hash calculation fails
           and remove the location by reverting image to queued
           state
        """
        try:
            image = self.image_repo.get(self.image_id)
            if image.status == 'importing':
                if not image.locations[0]['url'].startswith("http"):
                    # NOTE(pdeore): `http` store doesn't allow deletion of
                    # location:
                    image.locations.pop()
                image.status = 'queued'
            image.os_hash_algo = None
            self.image_repo.save(image)
        except exception.NotFound:
            LOG.debug("Image %s might have been deleted from the backend",
                      self.image_id)


class _VerifyValidationData(task.Task):

    def __init__(self, task_id, task_type, image_repo, image_id,
                 val_data):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        self.val_data = val_data
        super(_VerifyValidationData, self).__init__(
            name='%s-VerifyValidationData-%s' % (task_type, task_id))

    def execute(self):
        """Verify the Validation Data with calculated Hash

        :param image_id: Glance Image ID
        :val_data: Validation Data provider by user
        """
        image = self.image_repo.get(self.image_id)

        if self.val_data['os_hash_value'] != image.os_hash_value:
            msg = (_("os_hash_value: (%s) not matched with actual "
                     "os_hash_value: (%s)") % (
                   self.val_data['os_hash_value'],
                   image.os_hash_value))
            raise exception.InvalidParameterValue(msg)

    def revert(self, result, **kwargs):
        """Set image status back to queued and
           set the hash values to None
        """
        try:
            image = self.image_repo.get(self.image_id)
            if not image.locations[0]['url'].startswith("http"):
                # NOTE(pdeore): `http` store doesn't allow deletion of
                # location
                image.locations.pop()
            image.status = 'queued'
            image.os_hash_algo = None
            image.os_hash_value = None
            image.checksum = None
            self.image_repo.save(image)
        except exception.NotFound:
            LOG.debug("Image %s might have been deleted from the backend",
                      self.image_id)


class _SetHashValues(task.Task):

    def __init__(self, task_id, task_type, image_repo, image_id,
                 val_data):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        self.val_data = val_data
        super(_SetHashValues, self).__init__(
            name='%s-SetHashValues-%s' % (task_type, task_id))

    def execute(self):
        """Set user provided hash algo and value hash properties to image
           when do_secure_hash is False.

        :param image_id: Glance Image ID
        :val_data: Validation Data provided by user
        """
        image = self.image_repo.get(self.image_id)
        for k, v in self.val_data.items():
            setattr(image, k, v)
        self.image_repo.save(image)


class _UpdateLocationTask(task.Task):

    def __init__(self, task_id, task_type, image_repo, image_id, url,
                 context):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        self.url = url
        self.context = context
        super(_UpdateLocationTask, self).__init__(
            name='%s-UpdateLocationTask-%s' % (task_type, task_id))

    def execute(self):
        """Update the image location

        :param image_id: Glance Image ID
        :param url: Location URL
        """
        image = self.image_repo.get(self.image_id)
        try:
            # (NOTE(pdeore): Add metadata key to add the store identifier
            # as location metadata
            updated_location = {
                'url': self.url,
                'metadata': {},
            }
            if CONF.enabled_backends:
                updated_location = store_utils.get_updated_store_location(
                    [updated_location], context=self.context)[0]

            image.locations.append(updated_location)
            self.image_repo.save(image)
        except (exception.Invalid, exception.BadStoreUri) as e:
            raise _InvalidLocation(e.msg)


class _SetImageToActiveTask(task.Task):

    def __init__(self, task_id, task_type, image_repo, image_id):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        super(_SetImageToActiveTask, self).__init__(
            name='%s-SetImageToActiveTask-%s' % (task_type, task_id))

    def execute(self):
        """Set Image status to Active

        :param image_id: Glance Image ID
        """
        image = self.image_repo.get(self.image_id)
        image.status = 'active'
        self.image_repo.save(image)

    def revert(self, result, **kwargs):
        """Set image status back to queued and
           remove the location if it's added.
        """
        try:
            image = self.image_repo.get(self.image_id)
            if image.status != 'active':
                if not image.locations[0]['url'].startswith("http"):
                    # NOTE(pdeore): `http` store doesn't allow deletion of
                    # location
                    image.locations.pop()
                if image.status == 'importing':
                    image.status = 'queued'
            self.image_repo.save(image)
        except exception.NotFound:
            LOG.debug("Image %s might have been deleted from the backend",
                      self.image_id)


def get_flow(**kwargs):
    """Return task flow

    :param task_id: Task ID
    :param task_type: Type of the task
    :param task_repo: Task repo
    :param image_repo: Image repository used
    :param image_id: ID of the Image to be processed
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    task_repo = kwargs.get('task_repo')
    image_repo = kwargs.get('image_repo')
    admin_repo = kwargs.get('admin_repo')
    image_id = kwargs.get('image_id')
    val_data = kwargs.get('val_data', {})
    loc_url = kwargs.get('loc_url')
    context = kwargs.get('context')

    hashing_algo = val_data.get("os_hash_algo",
                                CONF['hashing_algorithm'])

    # Instantiate an action wrapper with the admin repo if we got one,
    # otherwise with the regular repo.
    action_wrapper = image_import.ImportActionWrapper(
        admin_repo or image_repo, image_id, task_id)
    kwargs['action_wrapper'] = action_wrapper

    flow = lf.Flow(task_type, retry=retry.AlwaysRevert())
    flow.add(image_import._ImageLock(task_id, task_type, action_wrapper))
    flow.add(
        _UpdateLocationTask(task_id, task_type, image_repo, image_id,
                            loc_url, context))
    if CONF.do_secure_hash:
        if val_data:
            flow.add(
                _CalculateHash(task_id, task_type, image_repo, image_id,
                               hashing_algo, status='importing'))
            flow.add(
                _VerifyValidationData(task_id, task_type, image_repo,
                                      image_id, val_data))
            flow.add(
                _SetImageToActiveTask(task_id, task_type, image_repo,
                                      image_id))
        else:
            flow.add(
                _SetImageToActiveTask(
                    task_id, task_type, image_repo, image_id))
            flow.add(
                _CalculateHash(task_id, task_type, image_repo, image_id,
                               hashing_algo))
    elif val_data:
        flow.add(
            _SetHashValues(task_id, task_type, image_repo, image_id,
                           val_data))
        flow.add(
            _SetImageToActiveTask(task_id, task_type, image_repo, image_id))
    else:
        flow.add(
            _SetImageToActiveTask(task_id, task_type, image_repo, image_id))

    flow.add(
        image_import._CompleteTask(task_id, task_type, task_repo,
                                   action_wrapper))

    return flow
