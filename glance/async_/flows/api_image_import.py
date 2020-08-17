# Copyright 2015 OpenStack Foundation
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
import functools
import os

import glance_store as store_api
from glance_store import backend
from glance_store import exceptions as store_exceptions
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import timeutils
from oslo_utils import units
import six
import taskflow
from taskflow.patterns import linear_flow as lf
from taskflow import retry
from taskflow import task

import glance.async_.flows._internal_plugins as internal_plugins
import glance.async_.flows.plugins as import_plugins
from glance.common import exception
from glance.common.scripts.image_import import main as image_import
from glance.common.scripts import utils as script_utils
from glance.common import store_utils
from glance.i18n import _, _LE, _LI


LOG = logging.getLogger(__name__)


CONF = cfg.CONF


api_import_opts = [
    cfg.ListOpt('image_import_plugins',
                item_type=cfg.types.String(quotes=True),
                bounds=True,
                sample_default='[no_op]',
                default=[],
                help=_("""
Image import plugins to be enabled for task processing.

Provide list of strings reflecting to the task Objects
that should be included to the Image Import flow. The
task objects needs to be defined in the 'glance/async/
flows/plugins/*' and may be implemented by OpenStack
Glance project team, deployer or 3rd party.

By default no plugins are enabled and to take advantage
of the plugin model the list of plugins must be set
explicitly in the glance-image-import.conf file.

The allowed values for this option is comma separated
list of object names in between ``[`` and ``]``.

Possible values:
    * no_op (only logs debug level message that the
      plugin has been executed)
    * Any provided Task object name to be included
      in to the flow.
""")),
]

CONF.register_opts(api_import_opts, group='image_import_opts')

# TODO(jokke): We should refactor the task implementations so that we do not
# need to duplicate what we have already for example in base_import.py.


class _NoStoresSucceeded(exception.GlanceException):

    def __init__(self, message):
        super(_NoStoresSucceeded, self).__init__(message)


class ImportActionWrapper(object):
    """Wrapper for all the image metadata operations we do during an import.

    This is used to consolidate the changes we make to image metadata during
    an import operation, and can be used with an admin-capable repo to
    enable non-owner controlled modification of that data if desired.

    Use this as a context manager to make multiple changes followed by
    a save of the image in one operation. An _ImportActions object is
    yielded from the context manager, which defines the available operations.

    :param image_repo: The ImageRepo we should use to fetch/save the image
    :param image-id: The ID of the image we should be altering
    """

    def __init__(self, image_repo, image_id, task_id):
        self._image_repo = image_repo
        self._image_id = image_id
        self._task_id = task_id

    def __enter__(self):
        self._image = self._image_repo.get(self._image_id)
        self._image_previous_status = self._image.status
        self._assert_task_lock(self._image)

        return _ImportActions(self._image)

    def __exit__(self, type, value, traceback):
        if type is not None:
            # NOTE(danms): Do not save the image if we raised in context
            return

        # NOTE(danms): If we were in the middle of a long-running
        # set_data() where someone else stole our lock, we may race
        # with them to update image locations and erase one that
        # someone else is working on. Checking the task lock here
        # again is not perfect exclusion, but in lieu of actual
        # thread-safe location updating, this at least reduces the
        # likelihood of that happening.
        self.assert_task_lock()

        if self._image_previous_status != self._image.status:
            LOG.debug('Image %(image_id)s status changing from '
                      '%(old_status)s to %(new_status)s',
                      {'image_id': self._image_id,
                       'old_status': self._image_previous_status,
                       'new_status': self._image.status})
        self._image_repo.save(self._image, self._image_previous_status)

    @property
    def image_id(self):
        return self._image_id

    def drop_lock_for_task(self):
        """Delete the import lock for our task.

        This is an atomic operation and thus does not require a context
        for the image save. Note that after calling this method, no
        further actions will be allowed on the image.

        :raises: NotFound if the image was not locked by the expected task.
        """
        image = self._image_repo.get(self._image_id)
        self._image_repo.delete_property_atomic(image,
                                                'os_glance_import_task',
                                                self._task_id)

    def _assert_task_lock(self, image):
        task_lock = image.extra_properties.get('os_glance_import_task')
        if task_lock != self._task_id:
            LOG.error('Image %(image)s import task %(task)s attempted to '
                      'take action on image, but other task %(other)s holds '
                      'the lock; Aborting.',
                      {'image': self._image_id,
                       'task': self._task_id,
                       'other': task_lock})
            raise exception.TaskAbortedError()

    def assert_task_lock(self):
        """Assert that we own the task lock on the image.

        :raises: TaskAbortedError if we do not
        """
        image = self._image_repo.get(self._image_id)
        self._assert_task_lock(image)


class _ImportActions(object):
    """Actions available for being performed on an image during import.

    This defines the available actions that can be performed on an image
    during import, which may be done with an image owned by another user.

    Do not instantiate this object directly, get it from ImportActionWrapper.
    """

    IMPORTING_STORES_KEY = 'os_glance_importing_to_stores'
    IMPORT_FAILED_KEY = 'os_glance_failed_import'

    def __init__(self, image):
        self._image = image

    @property
    def image_id(self):
        return self._image.image_id

    @property
    def image_status(self):
        return self._image.status

    def merge_store_list(self, list_key, stores, subtract=False):
        stores = set([store for store in stores if store])
        existing = set(
            self._image.extra_properties.get(list_key, '').split(','))

        if subtract:
            if stores - existing:
                LOG.debug('Stores %(stores)s not in %(key)s for '
                          'image %(image_id)s',
                          {'stores': ','.join(sorted(stores - existing)),
                           'key': list_key,
                           'image_id': self.image_id})
            merged_stores = existing - stores
        else:
            merged_stores = existing | stores

        stores_list = ','.join(sorted((store for store in
                                       merged_stores if store)))
        self._image.extra_properties[list_key] = stores_list
        LOG.debug('Image %(image_id)s %(key)s=%(stores)s',
                  {'image_id': self.image_id,
                   'key': list_key,
                   'stores': stores_list})

    def add_importing_stores(self, stores):
        """Add a list of stores to the importing list.

        Add stores to os_glance_importing_to_stores

        :param stores: A list of store names
        """
        self.merge_store_list(self.IMPORTING_STORES_KEY, stores)

    def remove_importing_stores(self, stores):
        """Remove a list of stores from the importing list.

        Remove stores from os_glance_importing_to_stores

        :param stores: A list of store names
        """
        self.merge_store_list(self.IMPORTING_STORES_KEY, stores, subtract=True)

    def add_failed_stores(self, stores):
        """Add a list of stores to the failed list.

        Add stores to os_glance_failed_import

        :param stores: A list of store names
        """
        self.merge_store_list(self.IMPORT_FAILED_KEY, stores)

    def remove_failed_stores(self, stores):
        """Remove a list of stores from the failed list.

        Remove stores from os_glance_failed_import

        :param stores: A list of store names
        """
        self.merge_store_list(self.IMPORT_FAILED_KEY, stores, subtract=True)

    def set_image_data(self, uri, task_id, backend, set_active,
                       callback=None):
        """Populate image with data on a specific backend.

        This is used during an image import operation to populate the data
        in a given store for the image. If this object wraps an admin-capable
        image_repo, then this will be done with admin credentials on behalf
        of a user already determined to be able to perform this operation
        (such as a copy-image import of an existing image owned by another
        user).

        :param uri: Source URL for image data
        :param task_id: The task responsible for this operation
        :param backend: The backend store to target the data
        :param set_active: Whether or not to set the image to 'active'
                           state after the operation completes
        :param callback: A callback function with signature:
                         fn(action, chunk_bytes, total_bytes)
                         which should be called while processing the image
                         approximately every minute.
        """
        if callback:
            callback = functools.partial(callback, self)
        return image_import.set_image_data(self._image, uri, task_id,
                                           backend=backend,
                                           set_active=set_active,
                                           callback=callback)

    def set_image_status(self, status):
        """Set the image status.

        :param status: The new status of the image
        """
        self._image.status = status

    def remove_location_for_store(self, backend):
        """Remove a location from an image given a backend store.

        Given a backend store, remove the corresponding location from the
        image's set of locations. If the last location is removed, remove
        the image checksum, hash information, and size.

        :param backend: The backend store to remove from the image
        """

        for i, location in enumerate(self._image.locations):
            if location.get('metadata', {}).get('store') == backend:
                try:
                    self._image.locations.pop(i)
                except (store_exceptions.NotFound,
                        store_exceptions.Forbidden):
                    msg = (_("Error deleting from store %(store)s when "
                             "reverting.") % {'store': backend})
                    LOG.warning(msg)
                # NOTE(yebinama): Some store drivers doesn't document which
                # exceptions they throw.
                except Exception:
                    msg = (_("Unexpected exception when deleting from store "
                             "%(store)s.") % {'store': backend})
                    LOG.warning(msg)
                else:
                    if len(self._image.locations) == 0:
                        self._image.checksum = None
                        self._image.os_hash_algo = None
                        self._image.os_hash_value = None
                        self._image.size = None
                break


class _DeleteFromFS(task.Task):

    def __init__(self, task_id, task_type):
        self.task_id = task_id
        self.task_type = task_type
        super(_DeleteFromFS, self).__init__(
            name='%s-DeleteFromFS-%s' % (task_type, task_id))

    def execute(self, file_path):
        """Remove file from the backend

        :param file_path: path to the file being deleted
        """
        if CONF.enabled_backends:
            try:
                store_api.delete(file_path, 'os_glance_staging_store')
            except store_api.exceptions.NotFound as e:
                LOG.error(_("After upload to backend, deletion of staged "
                            "image data from %(fn)s has failed because "
                            "%(em)s"), {'fn': file_path,
                                        'em': e.message})
        else:
            # TODO(abhishekk): After removal of backend module from
            # glance_store need to change this to use multi_backend
            # module.
            file_path = file_path[7:]
            if os.path.exists(file_path):
                try:
                    LOG.debug(_("After upload to the backend, deleting staged "
                                "image data from %(fn)s"), {'fn': file_path})
                    os.unlink(file_path)
                except OSError as e:
                    LOG.error(_("After upload to backend, deletion of staged "
                                "image data from %(fn)s has failed because "
                                "[Errno %(en)d]"), {'fn': file_path,
                                                    'en': e.errno})
            else:
                LOG.warning(_("After upload to backend, deletion of staged "
                              "image data has failed because "
                              "it cannot be found at %(fn)s"), {
                    'fn': file_path})


class _ImageLock(task.Task):
    def __init__(self, task_id, task_type, action_wrapper):
        self.task_id = task_id
        self.task_type = task_type
        self.action_wrapper = action_wrapper
        super(_ImageLock, self).__init__(
            name='%s-ImageLock-%s' % (task_type, task_id))

    def execute(self):
        self.action_wrapper.assert_task_lock()
        LOG.debug('Image %(image)s import task %(task)s lock confirmed',
                  {'image': self.action_wrapper.image_id,
                   'task': self.task_id})

    def revert(self, result, **kwargs):
        """Drop our claim on the image.

        If we have failed, we need to drop our import_task lock on the image
        so that something else can have a try. Note that we may have been
        preempted so we should only drop *our* lock.
        """
        try:
            self.action_wrapper.drop_lock_for_task()
        except exception.NotFound:
            LOG.warning('Image %(image)s import task %(task)s lost its '
                        'lock during execution!',
                        {'image': self.action_wrapper.image_id,
                         'task': self.task_id})
        else:
            LOG.debug('Image %(image)s import task %(task)s dropped '
                      'its lock after failure',
                      {'image': self.action_wrapper.image_id,
                       'task': self.task_id})


class _VerifyStaging(task.Task):

    # NOTE(jokke): This could be also for example "staging_path" but to
    # keep this compatible with other flows  we want to stay consistent
    # with base_import
    default_provides = 'file_path'

    def __init__(self, task_id, task_type, task_repo, uri):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        self.uri = uri
        super(_VerifyStaging, self).__init__(
            name='%s-ConfigureStaging-%s' % (task_type, task_id))

        # NOTE(jokke): If we want to use other than 'file' store in the
        # future, this is one thing that needs to change.
        try:
            uri.index('file:///', 0)
        except ValueError:
            msg = (_("%(task_id)s of %(task_type)s not configured "
                     "properly. Value of node_staging_uri must be "
                     " in format 'file://<absolute-path>'") %
                   {'task_id': self.task_id,
                    'task_type': self.task_type})
            raise exception.BadTaskConfiguration(msg)

        if not CONF.enabled_backends:
            # NOTE(jokke): We really don't need the store for anything but
            # verifying that we actually can build the store will allow us to
            # fail the flow early with clear message why that happens.
            self._build_store()

    def _build_store(self):
        # TODO(abhishekk): After removal of backend module from glance_store
        # need to change this to use multi_backend module.
        # NOTE(jokke): If we want to use some other store for staging, we can
        # implement the logic more general here. For now this should do.
        # NOTE(flaper87): Due to the nice glance_store api (#sarcasm), we're
        # forced to build our own config object, register the required options
        # (and by required I mean *ALL* of them, even the ones we don't want),
        # and create our own store instance by calling a private function.
        # This is certainly unfortunate but it's the best we can do until the
        # glance_store refactor is done. A good thing is that glance_store is
        # under our team's management and it gates on Glance so changes to
        # this API will (should?) break task's tests.
        conf = cfg.ConfigOpts()
        try:
            backend.register_opts(conf)
        except cfg.DuplicateOptError:
            pass
        conf.set_override('filesystem_store_datadir',
                          CONF.node_staging_uri[7:],
                          group='glance_store')

        # NOTE(flaper87): Do not even try to judge me for this... :(
        # With the glance_store refactor, this code will change, until
        # that happens, we don't have a better option and this is the
        # least worst one, IMHO.
        store = backend._load_store(conf, 'file')

        try:
            store.configure()
        except AttributeError:
            msg = (_("%(task_id)s of %(task_type)s not configured "
                     "properly. Could not load the filesystem store") %
                   {'task_id': self.task_id, 'task_type': self.task_type})
            raise exception.BadTaskConfiguration(msg)

    def execute(self):
        """Test the backend store and return the 'file_path'"""
        return self.uri


class _ImportToStore(task.Task):

    def __init__(self, task_id, task_type, task_repo, action_wrapper, uri,
                 backend, all_stores_must_succeed, set_active):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        self.action_wrapper = action_wrapper
        self.uri = uri
        self.backend = backend
        self.all_stores_must_succeed = all_stores_must_succeed
        self.set_active = set_active
        self.last_status = 0
        super(_ImportToStore, self).__init__(
            name='%s-ImportToStore-%s' % (task_type, task_id))

    def execute(self, file_path=None):
        """Bringing the imported image to back end store

        :param file_path: path to the image file
        """
        # NOTE(flaper87): Let's dance... and fall
        #
        # Unfortunatelly, because of the way our domain layers work and
        # the checks done in the FS store, we can't simply rename the file
        # and set the location. To do that, we'd have to duplicate the logic
        # of every and each of the domain factories (quota, location, etc)
        # and we'd also need to hack the FS store to prevent it from raising
        # a "duplication path" error. I'd rather have this task copying the
        # image bits one more time than duplicating all that logic.
        #
        # Since I don't think this should be the definitive solution, I'm
        # leaving the code below as a reference for what should happen here
        # once the FS store and domain code will be able to handle this case.
        #
        # if file_path is None:
        #    image_import.set_image_data(image, self.uri, None)
        #    return

        # NOTE(flaper87): Don't assume the image was stored in the
        # work_dir. Think in the case this path was provided by another task.
        # Also, lets try to neither assume things nor create "logic"
        # dependencies between this task and `_ImportToFS`
        #
        # base_path = os.path.dirname(file_path.split("file://")[-1])

        # NOTE(flaper87): Hopefully just scenarios #3 and #4. I say
        # hopefully because nothing prevents the user to use the same
        # FS store path as a work dir
        #
        # image_path = os.path.join(base_path, image_id)
        #
        # if (base_path == CONF.glance_store.filesystem_store_datadir or
        #      base_path in CONF.glance_store.filesystem_store_datadirs):
        #     os.rename(file_path, image_path)
        #
        # image_import.set_image_data(image, image_path, None)

        # NOTE(jokke): The different options here are kind of pointless as we
        # will need the file path anyways for our delete workflow for now.
        # For future proofing keeping this as is.

        with self.action_wrapper as action:
            self._execute(action, file_path)

    def _execute(self, action, file_path):
        self.last_status = timeutils.now()

        if action.image_status == "deleted":
            raise exception.ImportTaskError("Image has been deleted, aborting"
                                            " import.")
        try:
            action.set_image_data(file_path or self.uri,
                                  self.task_id, backend=self.backend,
                                  set_active=self.set_active,
                                  callback=self._status_callback)
        # NOTE(yebinama): set_image_data catches Exception and raises from
        # them. Can't be more specific on exceptions catched.
        except Exception:
            if self.all_stores_must_succeed:
                raise
            msg = (_("%(task_id)s of %(task_type)s failed but since "
                     "all_stores_must_succeed is set to false, continue.") %
                   {'task_id': self.task_id, 'task_type': self.task_type})
            LOG.warning(msg)
            if self.backend is not None:
                action.add_failed_stores([self.backend])

        if self.backend is not None:
            action.remove_importing_stores([self.backend])

    def _status_callback(self, action, chunk_bytes, total_bytes):
        # NOTE(danms): Only log status every five minutes
        if timeutils.now() - self.last_status > 300:
            LOG.debug('Image import %(image_id)s copied %(copied)i MiB',
                      {'image_id': action.image_id,
                       'copied': total_bytes // units.Mi})
            self.last_status = timeutils.now()

        task = script_utils.get_task(self.task_repo, self.task_id)
        if task is None:
            LOG.error(
                'Status callback for task %(task)s found no task object!',
                {'task': self.task_id})
            raise exception.TaskNotFound(self.task_id)
        if task.status != 'processing':
            LOG.error('Task %(task)s expected "processing" status, '
                      'but found "%(status)s"; aborting.')
            raise exception.TaskAbortedError()

        task.message = _('Copied %i MiB') % (total_bytes // units.Mi)
        self.task_repo.save(task)

    def revert(self, result, **kwargs):
        """
        Remove location from image in case of failure

        :param result: taskflow result object
        """
        with self.action_wrapper as action:
            action.remove_location_for_store(self.backend)
            action.remove_importing_stores([self.backend])
            if isinstance(result, taskflow.types.failure.Failure):
                # We are the store that failed, so add us to the failed list
                action.add_failed_stores([self.backend])


class _VerifyImageState(task.Task):

    def __init__(self, task_id, task_type, action_wrapper, import_method):
        self.task_id = task_id
        self.task_type = task_type
        self.action_wrapper = action_wrapper
        self.import_method = import_method
        super(_VerifyImageState, self).__init__(
            name='%s-VerifyImageState-%s' % (task_type, task_id))

    def execute(self):
        """Verify we have active image

        :param image_id: Glance Image ID
        """
        with self.action_wrapper as action:
            if action.image_status != 'active':
                raise _NoStoresSucceeded(_('None of the uploads finished!'))

    def revert(self, result, **kwargs):
        """Set back to queued if this wasn't copy-image job."""
        with self.action_wrapper as action:
            if self.import_method != 'copy-image':
                action.set_image_status('queued')


class _CompleteTask(task.Task):

    def __init__(self, task_id, task_type, task_repo, action_wrapper):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        self.action_wrapper = action_wrapper
        super(_CompleteTask, self).__init__(
            name='%s-CompleteTask-%s' % (task_type, task_id))

    def _finish_task(self, task):
        try:
            task.succeed({'image_id': self.action_wrapper.image_id})
        except Exception as e:
            # Note: The message string contains Error in it to indicate
            # in the task.message that it's a error message for the user.

            # TODO(nikhil): need to bring back save_and_reraise_exception when
            # necessary
            log_msg = _LE("Task ID %(task_id)s failed. Error: %(exc_type)s: "
                          "%(e)s")
            LOG.exception(log_msg, {'exc_type': six.text_type(type(e)),
                                    'e': encodeutils.exception_to_unicode(e),
                                    'task_id': task.task_id})

            err_msg = _("Error: %(exc_type)s: %(e)s")
            task.fail(err_msg % {'exc_type': six.text_type(type(e)),
                                 'e': encodeutils.exception_to_unicode(e)})
        finally:
            self.task_repo.save(task)

    def _drop_lock(self):
        try:
            self.action_wrapper.drop_lock_for_task()
        except exception.NotFound:
            # NOTE(danms): This would be really bad, but there is probably
            # not much point in reverting all the way back if we got this
            # far. Log the carnage for forensics.
            LOG.error('Image %(image)s import task %(task)s did not hold the '
                      'lock upon completion!',
                      {'image': self.action_wrapper.image_id,
                       'task': self.task_id})

    def execute(self):
        """Finishing the task flow

        :param image_id: Glance Image ID
        """
        task = script_utils.get_task(self.task_repo, self.task_id)
        if task is not None:
            self._finish_task(task)
        self._drop_lock()

        LOG.info(_LI("%(task_id)s of %(task_type)s completed"),
                 {'task_id': self.task_id, 'task_type': self.task_type})


def get_flow(**kwargs):
    """Return task flow

    :param task_id: Task ID
    :param task_type: Type of the task
    :param task_repo: Task repo
    :param image_repo: Image repository used
    :param image_id: ID of the Image to be processed
    :param uri: uri for the image file
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    task_repo = kwargs.get('task_repo')
    image_repo = kwargs.get('image_repo')
    admin_repo = kwargs.get('admin_repo')
    image_id = kwargs.get('image_id')
    import_method = kwargs.get('import_req')['method']['name']
    uri = kwargs.get('import_req')['method'].get('uri')
    stores = kwargs.get('backend', [None])
    all_stores_must_succeed = kwargs.get('import_req').get(
        'all_stores_must_succeed', True)

    separator = ''
    if not CONF.enabled_backends and not CONF.node_staging_uri.endswith('/'):
        separator = '/'

    # Instantiate an action wrapper with the admin repo if we got one,
    # otherwise with the regular repo.
    action_wrapper = ImportActionWrapper(admin_repo or image_repo, image_id,
                                         task_id)

    if not uri and import_method in ['glance-direct', 'copy-image']:
        if CONF.enabled_backends:
            separator, staging_dir = store_utils.get_dir_separator()
            uri = separator.join((staging_dir, str(image_id)))
        else:
            uri = separator.join((CONF.node_staging_uri, str(image_id)))

    flow = lf.Flow(task_type, retry=retry.AlwaysRevert())

    flow.add(_ImageLock(task_id, task_type, action_wrapper))

    if import_method in ['web-download', 'copy-image']:
        internal_plugin = internal_plugins.get_import_plugin(**kwargs)
        flow.add(internal_plugin)
        if CONF.enabled_backends:
            separator, staging_dir = store_utils.get_dir_separator()
            file_uri = separator.join((staging_dir, str(image_id)))
        else:
            file_uri = separator.join((CONF.node_staging_uri, str(image_id)))
    else:
        file_uri = uri

    flow.add(_VerifyStaging(task_id, task_type, task_repo, file_uri))

    # Note(jokke): The plugins were designed to act on the image data or
    # metadata during the import process before the image goes active. It
    # does not make sense to try to execute them during 'copy-image'.
    if import_method != 'copy-image':
        for plugin in import_plugins.get_import_plugins(**kwargs):
            flow.add(plugin)
    else:
        LOG.debug("Skipping plugins on 'copy-image' job.")

    for idx, store in enumerate(stores, 1):
        set_active = (not all_stores_must_succeed) or (idx == len(stores))
        if import_method == 'copy-image':
            set_active = False
        task_name = task_type + "-" + (store or "")
        import_task = lf.Flow(task_name)
        import_to_store = _ImportToStore(task_id,
                                         task_name,
                                         task_repo,
                                         action_wrapper,
                                         file_uri,
                                         store,
                                         all_stores_must_succeed,
                                         set_active)
        import_task.add(import_to_store)
        flow.add(import_task)

    delete_task = lf.Flow(task_type).add(_DeleteFromFS(task_id, task_type))
    flow.add(delete_task)

    verify_task = _VerifyImageState(task_id,
                                    task_type,
                                    action_wrapper,
                                    import_method)
    flow.add(verify_task)

    complete_task = _CompleteTask(task_id,
                                  task_type,
                                  task_repo,
                                  action_wrapper)
    flow.add(complete_task)

    with action_wrapper as action:
        if import_method != 'copy-image':
            action.set_image_status('importing')
        action.add_importing_stores(stores)
        action.remove_failed_stores(stores)

    return flow
