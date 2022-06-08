# Copyright 2013 IBM Corp.
# All Rights Reserved.
#
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy
import http.client as http
import urllib.parse as urlparse

import debtcollector
import glance_store
from oslo_config import cfg
from oslo_log import log as logging
import oslo_serialization.jsonutils as json
from oslo_utils import encodeutils
from oslo_utils import uuidutils
import webob.exc

from glance.api import common
from glance.api import policy
from glance.api.v2 import policy as api_policy
from glance.common import exception
from glance.common import timeutils
from glance.common import wsgi
import glance.db
import glance.gateway
from glance.i18n import _, _LW
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_opt('task_time_to_live', 'glance.common.config', group='task')

_DEPRECATION_MESSAGE = ("The task API is being deprecated and "
                        "it will be superseded by the new image import "
                        "API. Please refer to this link for more "
                        "information about the aforementioned process: "
                        "https://specs.openstack.org/openstack/glance-specs/"
                        "specs/mitaka/approved/image-import/"
                        "image-import-refactor.html")


class TasksController(object):
    """Manages operations on tasks."""

    def __init__(self, db_api=None, policy_enforcer=None, notifier=None,
                 store_api=None):
        self.db_api = db_api or glance.db.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.notifier = notifier or glance.notifier.Notifier()
        self.store_api = store_api or glance_store
        self.gateway = glance.gateway.Gateway(self.db_api, self.store_api,
                                              self.notifier, self.policy)

    @debtcollector.removals.remove(message=_DEPRECATION_MESSAGE)
    def create(self, req, task):
        # NOTE(rosmaita): access to this call is enforced in the deserializer

        ctxt = req.context
        task_factory = self.gateway.get_task_factory(ctxt)
        executor_factory = self.gateway.get_task_executor_factory(ctxt)
        task_repo = self.gateway.get_task_repo(ctxt)
        try:
            new_task = task_factory.new_task(
                task_type=task['type'],
                owner=ctxt.owner,
                task_input=task['input'],
                image_id=task['input'].get('image_id'),
                user_id=ctxt.user_id,
                request_id=ctxt.request_id)
            task_repo.add(new_task)
            task_executor = executor_factory.new_task_executor(ctxt)
            pool = common.get_thread_pool("tasks_pool")
            pool.spawn(new_task.run, task_executor)
        except exception.Forbidden as e:
            msg = (_LW("Forbidden to create task. Reason: %(reason)s")
                   % {'reason': encodeutils.exception_to_unicode(e)})
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        return new_task

    @debtcollector.removals.remove(message=_DEPRECATION_MESSAGE)
    def index(self, req, marker=None, limit=None, sort_key='created_at',
              sort_dir='desc', filters=None):
        # NOTE(rosmaita): access to this call is enforced in the deserializer

        result = {}
        if filters is None:
            filters = {}
        filters['deleted'] = False

        if limit is None:
            limit = CONF.limit_param_default
        limit = min(CONF.api_limit_max, limit)

        task_repo = self.gateway.get_task_stub_repo(req.context)
        try:
            tasks = task_repo.list(marker, limit, sort_key,
                                   sort_dir, filters)
            if len(tasks) != 0 and len(tasks) == limit:
                result['next_marker'] = tasks[-1].task_id
        except (exception.NotFound, exception.InvalidSortKey,
                exception.InvalidFilterRangeValue) as e:
            LOG.warning(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.Forbidden as e:
            LOG.warning(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        result['tasks'] = tasks
        return result

    @debtcollector.removals.remove(message=_DEPRECATION_MESSAGE)
    def get(self, req, task_id):
        _enforce_access_policy(self.policy, req)
        try:
            task_repo = self.gateway.get_task_repo(req.context)
            task = task_repo.get(task_id)
        except exception.NotFound as e:
            msg = (_LW("Failed to find task %(task_id)s. Reason: %(reason)s")
                   % {'task_id': task_id,
                      'reason': encodeutils.exception_to_unicode(e)})
            LOG.warning(msg)
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            msg = (_LW("Forbidden to get task %(task_id)s. Reason:"
                       " %(reason)s")
                   % {'task_id': task_id,
                      'reason': encodeutils.exception_to_unicode(e)})
            LOG.warning(msg)
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        return task

    @debtcollector.removals.remove(message=_DEPRECATION_MESSAGE)
    def delete(self, req, task_id):
        _enforce_access_policy(self.policy, req)
        msg = (_("This operation is currently not permitted on Glance Tasks. "
                 "They are auto deleted after reaching the time based on "
                 "their expires_at property."))
        raise webob.exc.HTTPMethodNotAllowed(explanation=msg,
                                             headers={'Allow': 'GET'},
                                             body_template='${explanation}')


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    _required_properties = ['type', 'input']

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    def _validate_sort_dir(self, sort_dir):
        if sort_dir not in ['asc', 'desc']:
            msg = _('Invalid sort direction: %s') % sort_dir
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_dir

    def _get_filters(self, filters):
        status = filters.get('status')
        if status:
            if status not in ['pending', 'processing', 'success', 'failure']:
                msg = _('Invalid status value: %s') % status
                raise webob.exc.HTTPBadRequest(explanation=msg)

        type = filters.get('type')
        if type:
            if type not in ['import']:
                msg = _('Invalid type value: %s') % type
                raise webob.exc.HTTPBadRequest(explanation=msg)

        return filters

    def _validate_marker(self, marker):
        if marker and not uuidutils.is_uuid_like(marker):
            msg = _('Invalid marker format')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return marker

    def _validate_limit(self, limit):
        try:
            limit = int(limit)
        except ValueError:
            msg = _("limit param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit < 0:
            msg = _("limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

    def _validate_create_body(self, body):
        """Validate the body of task creating request"""
        for param in self._required_properties:
            if param not in body:
                msg = _("Task '%s' is required") % param
                raise webob.exc.HTTPBadRequest(explanation=msg)

    def __init__(self, schema=None, policy_engine=None):
        super(RequestDeserializer, self).__init__()
        self.schema = schema or get_task_schema()
        # want to enforce the access policy as early as possible
        self.policy_engine = policy_engine or policy.Enforcer()

    def create(self, request):
        _enforce_access_policy(self.policy_engine, request)
        body = self._get_request_body(request)
        self._validate_create_body(body)
        try:
            self.schema.validate(body)
        except exception.InvalidObject as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        task = {}
        properties = body
        for key in self._required_properties:
            try:
                task[key] = properties.pop(key)
            except KeyError:
                pass
        return dict(task=task)

    def index(self, request):
        _enforce_access_policy(self.policy_engine, request)
        params = request.params.copy()
        limit = params.pop('limit', None)
        marker = params.pop('marker', None)
        sort_dir = params.pop('sort_dir', 'desc')
        query_params = {
            'sort_key': params.pop('sort_key', 'created_at'),
            'sort_dir': self._validate_sort_dir(sort_dir),
            'filters': self._get_filters(params)
        }

        if marker is not None:
            query_params['marker'] = self._validate_marker(marker)

        if limit is not None:
            query_params['limit'] = self._validate_limit(limit)
        return query_params


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, task_schema=None, partial_task_schema=None):
        super(ResponseSerializer, self).__init__()
        self.task_schema = task_schema or get_task_schema()
        self.partial_task_schema = (partial_task_schema
                                    or _get_partial_task_schema())

    def _inject_location_header(self, response, task):
        location = self._get_task_location(task)
        response.headers['Location'] = location

    def _get_task_location(self, task):
        return '/v2/tasks/%s' % task.task_id

    def _format_task(self, schema, task):
        task_view = {
            'id': task.task_id,
            'input': task.task_input,
            'type': task.type,
            'status': task.status,
            'owner': task.owner,
            'message': task.message,
            'result': task.result,
            'created_at': timeutils.isotime(task.created_at),
            'updated_at': timeutils.isotime(task.updated_at),
            'self': self._get_task_location(task),
            'schema': '/v2/schemas/task'
        }
        if task.image_id:
            task_view['image_id'] = task.image_id
        if task.request_id:
            task_view['request_id'] = task.request_id
        if task.user_id:
            task_view['user_id'] = task.user_id
        if task.expires_at:
            task_view['expires_at'] = timeutils.isotime(task.expires_at)
        task_view = schema.filter(task_view)  # domain
        return task_view

    def _format_task_stub(self, schema, task):
        task_view = {
            'id': task.task_id,
            'type': task.type,
            'status': task.status,
            'owner': task.owner,
            'created_at': timeutils.isotime(task.created_at),
            'updated_at': timeutils.isotime(task.updated_at),
            'self': self._get_task_location(task),
            'schema': '/v2/schemas/task'
        }
        if task.expires_at:
            task_view['expires_at'] = timeutils.isotime(task.expires_at)
        task_view = schema.filter(task_view)  # domain
        return task_view

    def create(self, response, task):
        response.status_int = http.CREATED
        self._inject_location_header(response, task)
        self.get(response, task)

    def get(self, response, task):
        task_view = self._format_task(self.task_schema, task)
        response.unicode_body = json.dumps(task_view, ensure_ascii=False)
        response.content_type = 'application/json'

    def index(self, response, result):
        params = dict(response.request.params)
        params.pop('marker', None)
        query = urlparse.urlencode(params)
        body = {
            'tasks': [self._format_task_stub(self.partial_task_schema, task)
                      for task in result['tasks']],
            'first': '/v2/tasks',
            'schema': '/v2/schemas/tasks',
        }
        if query:
            body['first'] = '%s?%s' % (body['first'], query)
        if 'next_marker' in result:
            params['marker'] = result['next_marker']
            next_query = urlparse.urlencode(params)
            body['next'] = '/v2/tasks?%s' % next_query
        response.unicode_body = json.dumps(body, ensure_ascii=False)
        response.content_type = 'application/json'


_TASK_SCHEMA = {
    "id": {
        "description": _("An identifier for the task"),
        "pattern": _('^([0-9a-fA-F]){8}-([0-9a-fA-F]){4}-([0-9a-fA-F]){4}'
                     '-([0-9a-fA-F]){4}-([0-9a-fA-F]){12}$'),
        "type": "string"
    },
    "type": {
        "description": _("The type of task represented by this content"),
        "enum": [
            "import",
            "api_image_import"
        ],
        "type": "string"
    },
    "status": {
        "description": _("The current status of this task"),
        "enum": [
            "pending",
            "processing",
            "success",
            "failure"
        ],
        "type": "string"
    },
    "input": {
        "description": _("The parameters required by task, JSON blob"),
        "type": ["null", "object"],
    },
    "result": {
        "description": _("The result of current task, JSON blob"),
        "type": ["null", "object"],
    },
    "owner": {
        "description": _("An identifier for the owner of this task"),
        "type": "string"
    },
    "message": {
        "description": _("Human-readable informative message only included"
                         " when appropriate (usually on failure)"),
        "type": "string",
    },
    "image_id": {
        "description": _("Image associated with the task"),
        "type": "string",
    },
    "request_id": {
        "description": _("Human-readable informative request-id"),
        "type": "string",
    },
    "user_id": {
        "description": _("User associated with the task"),
        "type": "string",
    },
    "expires_at": {
        "description": _("Datetime when this resource would be"
                         " subject to removal"),
        "type": ["null", "string"]
    },
    "created_at": {
        "description": _("Datetime when this resource was created"),
        "type": "string"
    },
    "updated_at": {
        "description": _("Datetime when this resource was updated"),
        "type": "string"
    },
    'self': {
        'readOnly': True,
        'type': 'string'
    },
    'schema': {
        'readOnly': True,
        'type': 'string'
    }
}


def _enforce_access_policy(policy_engine, request):
    api_policy.TasksAPIPolicy(
        request.context,
        enforcer=policy_engine).tasks_api_access()


def get_task_schema():
    properties = copy.deepcopy(_TASK_SCHEMA)
    schema = glance.schema.Schema('task', properties)
    return schema


def _get_partial_task_schema():
    properties = copy.deepcopy(_TASK_SCHEMA)
    hide_properties = ['input', 'result', 'message']
    for key in hide_properties:
        del properties[key]
    schema = glance.schema.Schema('task', properties)
    return schema


def get_collection_schema():
    task_schema = _get_partial_task_schema()
    return glance.schema.CollectionSchema('tasks', task_schema)


def create_resource():
    """Task resource factory method"""
    task_schema = get_task_schema()
    partial_task_schema = _get_partial_task_schema()
    deserializer = RequestDeserializer(task_schema)
    serializer = ResponseSerializer(task_schema, partial_task_schema)
    controller = TasksController()
    return wsgi.Resource(controller, deserializer, serializer)
