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

import futurist
from oslo_log import log as logging

from glance.i18n import _LE


LOG = logging.getLogger(__name__)


class TaskExecutor(object):
    """Base class for Asynchronous task executors. It does not support the
    execution mechanism.

    Provisions the extensible classes with necessary variables to utilize
    important Glance modules like, context, task_repo, image_repo,
    image_factory.

    Note:
        It also gives abstraction for the standard pre-processing and
        post-processing operations to be executed by a task. These may include
        validation checks, security checks, introspection, error handling etc.
        The aim is to give developers an abstract sense of the execution
        pipeline logic.

    Args:
        context: glance.context.RequestContext object for AuthZ and AuthN
            checks
        task_repo: glance.db.TaskRepo object which acts as a translator for
            glance.domain.Task and glance.domain.TaskStub objects
            into ORM semantics
        image_repo: glance.db.ImageRepo object which acts as a translator for
            glance.domain.Image object into ORM semantics
        image_factory: glance.domain.ImageFactory object to be used for
            creating new images for certain types of tasks viz. import, cloning
        admin_repo: glance.db.ImageRepo object which acts as a translator for
            glance.domain.Image object into ORM semantics, but with an admin
            context (optional)
    """

    def __init__(self, context, task_repo, image_repo, image_factory,
                 admin_repo=None):
        self.context = context
        self.task_repo = task_repo
        self.image_repo = image_repo
        self.image_factory = image_factory
        self.admin_repo = admin_repo

    def begin_processing(self, task_id):
        task = self.task_repo.get(task_id)
        task.begin_processing()
        self.task_repo.save(task)

        # start running
        self._run(task_id, task.type)

    def _run(self, task_id, task_type):
        task = self.task_repo.get(task_id)
        msg = _LE("This execution of Tasks is not setup. Please consult the "
                  "project documentation for more information on the "
                  "executors available.")
        LOG.error(msg)
        task.fail(_LE("Internal error occurred while trying to process task."))
        self.task_repo.save(task)


class ThreadPoolModel(object):
    """Base class for an abstract ThreadPool.

    Do not instantiate this directly, use one of the concrete
    implementations.
    """

    DEFAULTSIZE = 1

    @staticmethod
    def get_threadpool_executor_class():
        """Returns a futurist.ThreadPoolExecutor class."""
        pass

    def __init__(self, size=None):
        if size is None:
            size = self.DEFAULTSIZE

        threadpool_cls = self.get_threadpool_executor_class()
        LOG.debug('Creating threadpool model %r with size %i',
                  threadpool_cls.__name__, size)
        self.pool = threadpool_cls(size)

    def spawn(self, fn, *args, **kwargs):
        """Spawn a function with args using the thread pool."""
        LOG.debug('Spawning with %s: %s(%s, %s)',
                  self.get_threadpool_executor_class().__name__,
                  fn, args, kwargs)
        return self.pool.submit(fn, *args, **kwargs)

    def map(self, fn, iterable):
        """Map a function to each value in an iterable.

        This spawns a thread for each item in the provided iterable,
        generating results in the same order. Each item will spawn a
        thread, and each may run in parallel up to the limit of the
        pool.

        :param fn: A function to work on each item
        :param iterable: A sequence of items to process
        :returns: A generator of results in the same order
        """
        threads = []
        for i in iterable:
            threads.append(self.spawn(fn, i))
        for future in threads:
            yield future.result()


class EventletThreadPoolModel(ThreadPoolModel):
    """A ThreadPoolModel suitable for use with evenlet/greenthreads."""
    DEFAULTSIZE = 1024

    @staticmethod
    def get_threadpool_executor_class():
        return futurist.GreenThreadPoolExecutor


class NativeThreadPoolModel(ThreadPoolModel):
    """A ThreadPoolModel suitable for use with native threads."""
    DEFAULTSIZE = 16

    @staticmethod
    def get_threadpool_executor_class():
        return futurist.ThreadPoolExecutor


_THREADPOOL_MODEL = None


def set_threadpool_model(thread_type):
    """Set the system-wide threadpool model.

    This sets the type of ThreadPoolModel to use globally in the process.
    It should be called very early in init, and only once.

    :param thread_type: A string indicating the threading type in use,
                        either "eventlet" or "native"
    :raises: RuntimeError if the model is already set or some thread_type
             other than one of the supported ones is provided.
    """
    global _THREADPOOL_MODEL

    if thread_type == 'native':
        model = NativeThreadPoolModel
    elif thread_type == 'eventlet':
        model = EventletThreadPoolModel
    else:
        raise RuntimeError(
            ('Invalid thread type %r '
             '(must be "native" or "eventlet")') % (thread_type))

    if _THREADPOOL_MODEL is model:
        # Re-setting the same model is fine...
        return

    if _THREADPOOL_MODEL is not None:
        # ...changing it is not.
        raise RuntimeError('Thread model is already set')

    LOG.info('Threadpool model set to %r', model.__name__)
    _THREADPOOL_MODEL = model


def get_threadpool_model():
    """Returns the system-wide threadpool model class.

    This must be called after set_threadpool_model() whenever
    some code needs to know what the threadpool implementation is.

    This may only be called after set_threadpool_model() has been
    called to set the desired threading mode. If it is called before
    the model is set, it will raise AssertionError. This would likely
    be the case if this got run in a test before the model was
    initialized, or if glance modules that use threading were imported
    and run from some other code without setting the model first.

    :raises: AssertionError if the model has not yet been set.
    """
    global _THREADPOOL_MODEL
    assert _THREADPOOL_MODEL
    return _THREADPOOL_MODEL
