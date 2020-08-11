# Copyright 2014 OpenStack Foundation
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

__all__ = [
    'get_task',
    'unpack_task_input',
    'set_base_image_properties',
    'validate_location_uri',
    'get_image_data_iter',
]


from oslo_log import log as logging
from oslo_utils import timeutils
from six.moves import urllib

from glance.common import exception
from glance.i18n import _, _LE

LOG = logging.getLogger(__name__)


def get_task(task_repo, task_id):
    """Gets a TaskProxy object.

    :param task_repo: TaskRepo object used to perform DB operations
    :param task_id: ID of the Task
    """
    task = None
    try:
        task = task_repo.get(task_id)
    except exception.NotFound:
        msg = _LE('Task not found for task_id %s') % task_id
        LOG.exception(msg)

    return task


def unpack_task_input(task):
    """Verifies and returns valid task input dictionary.

    :param task: Task domain object
    """
    task_type = task.type
    task_input = task.task_input

    if task_type == 'api_image_import':
        if not task_input:
            msg = _("Input to api_image_import task is empty.")
            raise exception.Invalid(msg)
        if 'image_id' not in task_input:
            msg = _("Missing required 'image_id' field")
            raise exception.Invalid(msg)
    else:
        for key in ["import_from", "import_from_format", "image_properties"]:
            if key not in task_input:
                msg = (_("Input does not contain '%(key)s' field") %
                       {"key": key})
                raise exception.Invalid(msg)

    return task_input


def set_base_image_properties(properties=None):
    """Sets optional base properties for creating Image.

    :param properties: Input dict to set some base properties
    """
    if isinstance(properties, dict) and len(properties) == 0:
        # TODO(nikhil): We can make these properties configurable while
        # implementing the pipeline logic for the scripts. The below shown
        # are placeholders to show that the scripts work on 'devstack'
        # environment.
        properties['disk_format'] = 'qcow2'
        properties['container_format'] = 'bare'


def validate_location_uri(location):
    """Validate location uri into acceptable format.

    :param location: Location uri to be validated
    """
    if not location:
        raise exception.BadStoreUri(_('Invalid location: %s') % location)

    elif location.startswith(('http://', 'https://')):
        return location

    # NOTE: file type uri is being avoided for security reasons,
    # see LP bug #942118 #1400966.
    elif location.startswith(("file:///", "filesystem:///")):
        msg = _("File based imports are not allowed. Please use a non-local "
                "source of image data.")
        # NOTE: raise BadStoreUri and let the encompassing block save the error
        # msg in the task.message.
        raise exception.BadStoreUri(msg)

    else:
        # TODO(nikhil): add other supported uris
        supported = ['http', ]
        msg = _("The given uri is not valid. Please specify a "
                "valid uri from the following list of supported uri "
                "%(supported)s") % {'supported': supported}
        raise urllib.error.URLError(msg)


def get_image_data_iter(uri):
    """Returns iterable object either for local file or uri

    :param uri: uri (remote or local) to the datasource we want to iterate

    Validation/sanitization of the uri is expected to happen before we get
    here.
    """
    # NOTE(flaper87): This is safe because the input uri is already
    # verified before the task is created.
    if uri.startswith("file://"):
        uri = uri.split("file://")[-1]
        # NOTE(flaper87): The caller of this function expects to have
        # an iterable object. FileObjects in python are iterable, therefore
        # we are returning it as is.
        # The file descriptor will be eventually cleaned up by the garbage
        # collector once its ref-count is dropped to 0. That is, when there
        # wont be any references pointing to this file.
        #
        # We're not using StringIO or other tools to avoid reading everything
        # into memory. Some images may be quite heavy.
        return open(uri, "rb")

    return urllib.request.urlopen(uri)


class CallbackIterator(object):
    """A proxy iterator that calls a callback function periodically

    This is used to wrap a reading file object and proxy its chunks
    through to another caller. Periodically, the callback function
    will be called with information about the data processed so far,
    allowing for status updating or cancel flag checking. The function
    can be called every time we process a chunk, or only after we have
    processed a certain amount of data since the last call.

    :param source: A source iterator whose content will be proxied
                   through this object.
    :param callback: A function to be called periodically while iterating.
                     The signature should be fn(chunk_bytes, total_bytes),
                     where chunk is the number of bytes since the last
                     call of the callback, and total_bytes is the total amount
                     copied thus far.
    :param min_interval: Limit the calls to callback to only when this many
                         seconds have elapsed since the last callback (a
                         close() or final iteration may fire the callback in
                         less time to ensure completion).
    """

    def __init__(self, source, callback, min_interval=None):
        self._source = source
        self._callback = callback
        self._min_interval = min_interval
        self._chunk_bytes = 0
        self._total_bytes = 0
        self._timer = None

    @property
    def callback_due(self):
        """Indicates if a callback should be made.

        If no time-based limit is set, this will always be True.
        If a limit is set, then this returns True exactly once,
        resetting the timer when it does.
        """
        if not self._min_interval:
            return True

        if not self._timer:
            self._timer = timeutils.StopWatch(self._min_interval)
            self._timer.start()

        if self._timer.expired():
            self._timer.restart()
            return True
        else:
            return False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self._source)
        except StopIteration:
            # NOTE(danms): Make sure we call the callback the last
            # time if we have processed data since the last one.
            self._call_callback(b'', is_last=True)
            raise

        self._call_callback(chunk)
        return chunk

    def close(self):
        self._call_callback(b'', is_last=True)
        if hasattr(self._source, 'close'):
            return self._source.close()

    def _call_callback(self, chunk, is_last=False):
        self._total_bytes += len(chunk)
        self._chunk_bytes += len(chunk)

        if not self._chunk_bytes:
            # NOTE(danms): Never call the callback if we haven't processed
            # any data since the last time
            return

        if is_last or self.callback_due:
            # FIXME(danms): Perhaps we should only abort the read if
            # the callback raises a known abort exception, otherwise
            # log and swallow. Need to figure out what exception
            # read() callers would be expecting that we could raise
            # from here.
            self._callback(self._chunk_bytes, self._total_bytes)
            self._chunk_bytes = 0

    def read(self, size=None):
        chunk = self._source.read(size)
        self._call_callback(chunk)
        return chunk
