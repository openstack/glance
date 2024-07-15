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

import json
import os

import glance_store as store_api
from glance_store import backend
from oslo_concurrency import processutils as putils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import excutils
from stevedore import named
from taskflow.patterns import linear_flow as lf
from taskflow import retry
from taskflow import task
from taskflow.types import failure

from glance.async_ import utils
from glance.common import exception
from glance.common.scripts.image_import import main as image_import
from glance.common.scripts import utils as script_utils
from glance.i18n import _, _LE, _LI


LOG = logging.getLogger(__name__)


CONF = cfg.CONF


class _CreateImage(task.Task):

    default_provides = 'image_id'

    def __init__(self, task_id, task_type, task_repo, image_repo,
                 image_factory):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        self.image_repo = image_repo
        self.image_factory = image_factory
        super(_CreateImage, self).__init__(
            name='%s-CreateImage-%s' % (task_type, task_id))

    def execute(self):
        task = script_utils.get_task(self.task_repo, self.task_id)
        if task is None:
            return
        task_input = script_utils.unpack_task_input(task)
        image = image_import.create_image(
            self.image_repo, self.image_factory,
            task_input.get('image_properties'), self.task_id)

        LOG.debug("Task %(task_id)s created image %(image_id)s",
                  {'task_id': task.task_id, 'image_id': image.image_id})
        return image.image_id

    def revert(self, *args, **kwargs):
        # TODO(NiallBunting): Deleting the image like this could be considered
        # a brute force way of reverting images. It may be worth checking if
        # data has been written.
        result = kwargs.get('result', None)
        if result is not None:
            if kwargs.get('flow_failures', None) is not None:
                image = self.image_repo.get(result)
                LOG.debug("Deleting image whilst reverting.")
                image.delete()
                self.image_repo.remove(image)


class _ImportToFS(task.Task):

    default_provides = 'file_path'

    def __init__(self, task_id, task_type, task_repo, uri):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        self.uri = uri
        super(_ImportToFS, self).__init__(
            name='%s-ImportToFS-%s' % (task_type, task_id))

        # NOTE(abhishekk): Use reserved 'os_glance_tasks_store' for tasks,
        # the else part will be removed once old way of configuring store
        # is deprecated.
        if CONF.enabled_backends:
            self.store = store_api.get_store_from_store_identifier(
                'os_glance_tasks_store')
        else:
            if CONF.task.work_dir is None:
                msg = (_("%(task_id)s of %(task_type)s not configured "
                         "properly. Missing work dir: %(work_dir)s") %
                       {'task_id': self.task_id,
                        'task_type': self.task_type,
                        'work_dir': CONF.task.work_dir})
                raise exception.BadTaskConfiguration(msg)

            self.store = self._build_store()

    def _build_store(self):
        # NOTE(flaper87): Due to the nice glance_store api (#sarcasm), we're
        # forced to build our own config object, register the required options
        # (and by required I mean *ALL* of them, even the ones we don't want),
        # and create our own store instance by calling a private function.
        # This is certainly unfortunate but it's the best we can do until the
        # glance_store refactor is done. A good thing is that glance_store is
        # under our team's management and it gates on Glance so changes to
        # this API will (should?) break task's tests.
        conf = cfg.ConfigOpts()
        backend.register_opts(conf)
        conf.set_override('filesystem_store_datadir',
                          CONF.task.work_dir,
                          group='glance_store')

        # NOTE(flaper87): Do not even try to judge me for this... :(
        # With the glance_store refactor, this code will change, until
        # that happens, we don't have a better option and this is the
        # least worst one, IMHO.
        store = backend._load_store(conf, 'file')

        if store is None:
            msg = (_("%(task_id)s of %(task_type)s not configured "
                     "properly. Could not load the filesystem store") %
                   {'task_id': self.task_id, 'task_type': self.task_type})
            raise exception.BadTaskConfiguration(msg)

        store.configure()
        return store

    def execute(self, image_id):
        """Create temp file into store and return path to it

        :param image_id: Glance Image ID
        """
        # NOTE(flaper87): We've decided to use a separate `work_dir` for
        # this task - and tasks coming after this one - as a way to expect
        # users to configure a local store for pre-import works on the image
        # to happen.
        #
        # While using any path should be "technically" fine, it's not what
        # we recommend as the best solution. For more details on this, please
        # refer to the comment in the `_ImportToStore.execute` method.
        data = script_utils.get_image_data_iter(self.uri)

        path = self.store.add(image_id, data, 0, context=None)[0]

        try:
            # NOTE(flaper87): Consider moving this code to a common
            # place that other tasks can consume as well.
            stdout, stderr = putils.trycmd('qemu-img', 'info',
                                           '--output=json', path,
                                           prlimit=utils.QEMU_IMG_PROC_LIMITS,
                                           log_errors=putils.LOG_ALL_ERRORS)
        except OSError as exc:
            with excutils.save_and_reraise_exception():
                exc_message = encodeutils.exception_to_unicode(exc)
                msg = _LE('Failed to execute security checks on the image '
                          '%(task_id)s: %(exc)s')
                LOG.error(msg, {'task_id': self.task_id, 'exc': exc_message})

        metadata = json.loads(stdout)

        backing_file = metadata.get('backing-filename')
        if backing_file is not None:
            msg = _("File %(path)s has invalid backing file "
                    "%(bfile)s, aborting.") % {'path': path,
                                               'bfile': backing_file}
            raise RuntimeError(msg)

        try:
            data_file = metadata['format-specific']['data']['data-file']
        except KeyError:
            data_file = None
        if data_file is not None:
            msg = _("File %(path)s has invalid data-file "
                    "%(dfile)s, aborting.") % {"path": path,
                                               "dfile": data_file}
            raise RuntimeError(msg)

        return path

    def revert(self, image_id, result, **kwargs):
        if isinstance(result, failure.Failure):
            LOG.exception(_LE('Task: %(task_id)s failed to import image '
                              '%(image_id)s to the filesystem.'),
                          {'task_id': self.task_id, 'image_id': image_id})
            return

        if os.path.exists(result.split("file://")[-1]):
            if CONF.enabled_backends:
                store_api.delete(result, 'os_glance_tasks_store')
            else:
                store_api.delete_from_backend(result)


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
            store_api.delete(file_path, 'os_glance_tasks_store')
        else:
            store_api.delete_from_backend(file_path)


class _ImportToStore(task.Task):

    def __init__(self, task_id, task_type, image_repo, uri, backend):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.uri = uri
        self.backend = backend
        super(_ImportToStore, self).__init__(
            name='%s-ImportToStore-%s' % (task_type, task_id))

    def execute(self, image_id, file_path=None):
        """Bringing the introspected image to back end store

        :param image_id: Glance Image ID
        :param file_path: path to the image file
        """
        # NOTE(flaper87): There are a couple of interesting bits in the
        # interaction between this task and the `_ImportToFS` one. I'll try
        # to cover them in this comment.
        #
        # NOTE(flaper87):
        # `_ImportToFS` downloads the image to a dedicated `work_dir` which
        # needs to be configured in advance (please refer to the config option
        # docs for more info). The motivation behind this is also explained in
        # the `_ImportToFS.execute` method.
        #
        # Due to the fact that we have an `_ImportToFS` task which downloads
        # the image data already, we need to be as smart as we can in this task
        # to avoid downloading the data several times and reducing the copy or
        # write times. There are several scenarios where the interaction
        # between this task and `_ImportToFS` could be improved. All these
        # scenarios assume the `_ImportToFS` task has been executed before
        # and/or in a more abstract scenario, that `file_path` is being
        # provided.
        #
        # Scenario 1: FS Store is Remote, introspection enabled,
        # conversion disabled
        #
        # In this scenario, the user would benefit from having the scratch path
        # being the same path as the fs store. Only one write would happen and
        # an extra read will happen in order to introspect the image. Note that
        # this read is just for the image headers and not the entire file.
        #
        # Scenario 2: FS Store is remote, introspection enabled,
        # conversion enabled
        #
        # In this scenario, the user would benefit from having a *local* store
        # into which the image can be converted. This will require downloading
        # the image locally, converting it and then copying the converted image
        # to the remote store.
        #
        # Scenario 3: FS Store is local, introspection enabled,
        # conversion disabled
        # Scenario 4: FS Store is local, introspection enabled,
        # conversion enabled
        #
        # In both these scenarios the user shouldn't care if the FS
        # store path and the work dir are the same, therefore probably
        # benefit, about the scratch path and the FS store being the
        # same from a performance perspective. Space wise, regardless
        # of the scenario, the user will have to account for it in
        # advance.
        #
        # Lets get to it and identify the different scenarios in the
        # implementation
        image = self.image_repo.get(image_id)
        image.status = 'saving'
        self.image_repo.save(image)

        # NOTE(flaper87): Let's dance... and fall
        #
        # Unfortunately, because of the way our domain layers work and
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
        try:
            image_import.set_image_data(image,
                                        file_path or self.uri, self.task_id,
                                        backend=self.backend)
        except IOError as e:
            msg = (_('Uploading the image failed due to: %(exc)s') %
                   {'exc': encodeutils.exception_to_unicode(e)})
            LOG.error(msg)
            raise exception.UploadException(message=msg)
        # NOTE(flaper87): We need to save the image again after the locations
        # have been set in the image.
        self.image_repo.save(image)


class _SaveImage(task.Task):

    def __init__(self, task_id, task_type, image_repo):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        super(_SaveImage, self).__init__(
            name='%s-SaveImage-%s' % (task_type, task_id))

    def execute(self, image_id):
        """Transition image status to active

        :param image_id: Glance Image ID
        """
        new_image = self.image_repo.get(image_id)
        if new_image.status == 'saving':
            # NOTE(flaper87): THIS IS WRONG!
            # we should be doing atomic updates to avoid
            # race conditions. This happens in other places
            # too.
            new_image.status = 'active'
        self.image_repo.save(new_image)


class _CompleteTask(task.Task):

    def __init__(self, task_id, task_type, task_repo):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        super(_CompleteTask, self).__init__(
            name='%s-CompleteTask-%s' % (task_type, task_id))

    def execute(self, image_id):
        """Finishing the task flow

        :param image_id: Glance Image ID
        """
        task = script_utils.get_task(self.task_repo, self.task_id)
        if task is None:
            return
        try:
            task.succeed({'image_id': image_id})
        except Exception as e:
            # Note: The message string contains Error in it to indicate
            # in the task.message that it's a error message for the user.

            # TODO(nikhil): need to bring back save_and_reraise_exception when
            # necessary
            log_msg = _LE("Task ID %(task_id)s failed. Error: %(exc_type)s: "
                          "%(e)s")
            LOG.exception(log_msg, {'exc_type': str(type(e)),
                                    'e': encodeutils.exception_to_unicode(e),
                                    'task_id': task.task_id})

            err_msg = _("Error: %(exc_type)s: %(e)s")
            task.fail(err_msg % {'exc_type': str(type(e)),
                                 'e': encodeutils.exception_to_unicode(e)})
        finally:
            self.task_repo.save(task)

        LOG.info(_LI("%(task_id)s of %(task_type)s completed"),
                 {'task_id': self.task_id, 'task_type': self.task_type})


def _get_import_flows(**kwargs):
    # NOTE(flaper87): Until we have a better infrastructure to enable
    # and disable tasks plugins, hard-code the tasks we know exist,
    # instead of loading everything from the namespace. This guarantees
    # both, the load order of these plugins and the fact that no random
    # plugins will be added/loaded until we feel comfortable with this.
    # Future patches will keep using NamedExtensionManager but they'll
    # rely on a config option to control this process.
    extensions = named.NamedExtensionManager('glance.flows.import',
                                             names=['ovf_process',
                                                    'convert',
                                                    'introspect'],
                                             name_order=True,
                                             invoke_on_load=True,
                                             invoke_kwds=kwargs)

    for ext in extensions.extensions:
        yield ext.obj


def get_flow(**kwargs):
    """Return task flow

    :param task_id: Task ID
    :param task_type: Type of the task
    :param task_repo: Task repo
    :param image_repo: Image repository used
    :param image_factory: Glance Image Factory
    :param uri: uri for the image file
    """
    task_id = kwargs.get('task_id')
    task_type = kwargs.get('task_type')
    task_repo = kwargs.get('task_repo')
    image_repo = kwargs.get('image_repo')
    image_factory = kwargs.get('image_factory')
    uri = kwargs.get('uri')
    backend = kwargs.get('backend')

    flow = lf.Flow(task_type, retry=retry.AlwaysRevert()).add(
        _CreateImage(task_id, task_type, task_repo, image_repo, image_factory))

    import_to_store = _ImportToStore(task_id, task_type, image_repo, uri,
                                     backend)

    try:
        # NOTE(flaper87): ImportToLocal and DeleteFromLocal shouldn't be here.
        # Ideally, we should have the different import flows doing this for us
        # and this function should clean up duplicated tasks. For example, say
        # 2 flows need to have a local copy of the image - ImportToLocal - in
        # order to be able to complete the task - i.e Introspect-. In that
        # case, the introspect.get_flow call should add both, ImportToLocal and
        # DeleteFromLocal, to the flow and this function will reduce the
        # duplicated calls to those tasks by creating a linear flow that
        # ensures those are called before the other tasks.  For now, I'm
        # keeping them here, though.
        limbo = lf.Flow(task_type).add(_ImportToFS(task_id,
                                                   task_type,
                                                   task_repo,
                                                   uri))

        for subflow in _get_import_flows(**kwargs):
            limbo.add(subflow)

        # NOTE(flaper87): We have hard-coded 2 tasks,
        # if there aren't more than 2, it means that
        # no subtask has been registered.
        if len(limbo) > 1:
            flow.add(limbo)

            # NOTE(flaper87): Until this implementation gets smarter,
            # make sure ImportToStore is called *after* the imported
            # flow stages. If not, the image will be set to saving state
            # invalidating tasks like Introspection or Convert.
            flow.add(import_to_store)

            # NOTE(flaper87): Since this is an "optional" task but required
            # when `limbo` is executed, we're adding it in its own subflow
            # to isolate it from the rest of the flow.
            delete_flow = lf.Flow(task_type).add(_DeleteFromFS(task_id,
                                                               task_type))
            flow.add(delete_flow)
        else:
            flow.add(import_to_store)
    except exception.BadTaskConfiguration as exc:
        # NOTE(flaper87): If something goes wrong with the load of
        # import tasks, make sure we go on.
        LOG.error(_LE('Bad task configuration: %s'), exc.message)
        flow.add(import_to_store)

    flow.add(
        _SaveImage(task_id, task_type, image_repo),
        _CompleteTask(task_id, task_type, task_repo)
    )
    return flow
