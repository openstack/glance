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
import os

import glance_store as store_api
from glance_store import backend
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
import six
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
            store_api.delete(file_path, 'os_glance_staging_store')
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

    def __init__(self, task_id, task_type, image_repo, uri, image_id, backend):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.uri = uri
        self.image_id = image_id
        self.backend = backend
        super(_ImportToStore, self).__init__(
            name='%s-ImportToStore-%s' % (task_type, task_id))

    def execute(self, file_path=None):
        """Bringing the imported image to back end store

        :param image_id: Glance Image ID
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
        image = self.image_repo.get(self.image_id)
        image_import.set_image_data(image, file_path or self.uri, self.task_id,
                                    backend=self.backend)

        # NOTE(flaper87): We need to save the image again after the locations
        # have been set in the image.
        self.image_repo.save(image)


class _SaveImage(task.Task):

    def __init__(self, task_id, task_type, image_repo, image_id):
        self.task_id = task_id
        self.task_type = task_type
        self.image_repo = image_repo
        self.image_id = image_id
        super(_SaveImage, self).__init__(
            name='%s-SaveImage-%s' % (task_type, task_id))

    def execute(self):
        """Transition image status to active

        :param image_id: Glance Image ID
        """
        new_image = self.image_repo.get(self.image_id)
        if new_image.status == 'saving':
            # NOTE(flaper87): THIS IS WRONG!
            # we should be doing atomic updates to avoid
            # race conditions. This happens in other places
            # too.
            new_image.status = 'active'
        self.image_repo.save(new_image)


class _CompleteTask(task.Task):

    def __init__(self, task_id, task_type, task_repo, image_id):
        self.task_id = task_id
        self.task_type = task_type
        self.task_repo = task_repo
        self.image_id = image_id
        super(_CompleteTask, self).__init__(
            name='%s-CompleteTask-%s' % (task_type, task_id))

    def execute(self):
        """Finishing the task flow

        :param image_id: Glance Image ID
        """
        task = script_utils.get_task(self.task_repo, self.task_id)
        if task is None:
            return
        try:
            task.succeed({'image_id': self.image_id})
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
    image_id = kwargs.get('image_id')
    import_method = kwargs.get('import_req')['method']['name']
    uri = kwargs.get('import_req')['method'].get('uri')
    backend = kwargs.get('backend')

    separator = ''
    if not CONF.enabled_backends and not CONF.node_staging_uri.endswith('/'):
        separator = '/'

    if not uri and import_method == 'glance-direct':
        if CONF.enabled_backends:
            separator, staging_dir = store_utils.get_dir_separator()
            uri = separator.join((staging_dir, str(image_id)))
        else:
            uri = separator.join((CONF.node_staging_uri, str(image_id)))

    flow = lf.Flow(task_type, retry=retry.AlwaysRevert())

    if import_method == 'web-download':
        downloadToStaging = internal_plugins.get_import_plugin(**kwargs)
        flow.add(downloadToStaging)
        if CONF.enabled_backends:
            separator, staging_dir = store_utils.get_dir_separator()
            file_uri = separator.join((staging_dir, str(image_id)))
        else:
            file_uri = separator.join((CONF.node_staging_uri, str(image_id)))
    else:
        file_uri = uri

    flow.add(_VerifyStaging(task_id, task_type, task_repo, file_uri))

    for plugin in import_plugins.get_import_plugins(**kwargs):
        flow.add(plugin)

    import_to_store = _ImportToStore(task_id,
                                     task_type,
                                     image_repo,
                                     file_uri,
                                     image_id,
                                     backend)
    flow.add(import_to_store)

    delete_task = lf.Flow(task_type).add(_DeleteFromFS(task_id, task_type))
    flow.add(delete_task)

    save_task = _SaveImage(task_id,
                           task_type,
                           image_repo,
                           image_id)
    flow.add(save_task)

    complete_task = _CompleteTask(task_id,
                                  task_type,
                                  task_repo,
                                  image_id)
    flow.add(complete_task)

    image = image_repo.get(image_id)
    from_state = image.status
    image.status = 'importing'
    image_repo.save(image, from_state=from_state)

    return flow
