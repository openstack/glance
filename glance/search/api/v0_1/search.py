# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

from oslo.config import cfg
from oslo_log import log as logging
import six
import webob.exc

from glance.api import policy
from glance.common import exception
from glance.common import utils
from glance.common import wsgi
import glance.db
import glance.gateway
from glance import i18n
import glance.notifier
import glance.schema

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE

CONF = cfg.CONF


class SearchController(object):
    def __init__(self, plugins=None, es_api=None, policy_enforcer=None):
        self.es_api = es_api or glance.search.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.gateway = glance.gateway.Gateway(
            es_api=self.es_api,
            policy_enforcer=self.policy)
        self.plugins = plugins or []

    def search(self, req, query, index, doc_type=None, fields=None, offset=0,
               limit=10):
        if fields is None:
            fields = []

        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            result = search_repo.search(index,
                                        doc_type,
                                        query,
                                        fields,
                                        offset,
                                        limit,
                                        True)

            for plugin in self.plugins:
                result = plugin.obj.filter_result(result, req.context)

            return result
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(utils.exception_to_str(e))
            raise webob.exc.HTTPInternalServerError()

    def plugins_info(self, req):
        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            return search_repo.plugins_info()
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(utils.exception_to_str(e))
            raise webob.exc.HTTPInternalServerError()

    def index(self, req, actions, default_index=None, default_type=None):
        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            success, errors = search_repo.index(
                default_index,
                default_type,
                actions)
            return {
                'success': success,
                'failed': len(errors),
                'errors': errors,
            }

        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except Exception as e:
            LOG.error(utils.exception_to_str(e))
            raise webob.exc.HTTPInternalServerError()


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    _disallowed_properties = ['self', 'schema']

    def __init__(self, plugins, schema=None):
        super(RequestDeserializer, self).__init__()
        self.plugins = plugins

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    @classmethod
    def _check_allowed(cls, query):
        for key in cls._disallowed_properties:
            if key in query:
                msg = _("Attribute '%s' is read-only.") % key
                raise webob.exc.HTTPForbidden(explanation=msg)

    def _get_available_indices(self):
        return list(set([p.obj.get_index_name() for p in self.plugins]))

    def _get_available_types(self):
        return list(set([p.obj.get_document_type() for p in self.plugins]))

    def _validate_index(self, index):
        available_indices = self._get_available_indices()

        if index not in available_indices:
            msg = _("Index '%s' is not supported.") % index
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return index

    def _validate_doc_type(self, doc_type):
        available_types = self._get_available_types()

        if doc_type not in available_types:
            msg = _("Document type '%s' is not supported.") % doc_type
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return doc_type

    def _validate_offset(self, offset):
        try:
            offset = int(offset)
        except ValueError:
            msg = _("offset param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if offset < 0:
            msg = _("offset param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return offset

    def _validate_limit(self, limit):
        try:
            limit = int(limit)
        except ValueError:
            msg = _("limit param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit < 1:
            msg = _("limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

    def _validate_actions(self, actions):
        if not actions:
            msg = _("actions param cannot be empty")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        output = []
        allowed_action_types = ['create', 'update', 'delete', 'index']
        for action in actions:
            action_type = action.get('action', 'index')
            document_id = action.get('id')
            document_type = action.get('type')
            index_name = action.get('index')
            data = action.get('data', {})
            script = action.get('script')

            if index_name is not None:
                index_name = self._validate_index(index_name)

            if document_type is not None:
                document_type = self._validate_doc_type(document_type)

            if action_type not in allowed_action_types:
                msg = _("Invalid action type: '%s'") % action_type
                raise webob.exc.HTTPBadRequest(explanation=msg)
            elif (action_type in ['create', 'update', 'index'] and
                    not any([data, script])):
                msg = (_("Action type '%s' requires data or script param.") %
                       action_type)
                raise webob.exc.HTTPBadRequest(explanation=msg)
            elif action_type in ['update', 'delete'] and not document_id:
                msg = (_("Action type '%s' requires ID of the document.") %
                       action_type)
                raise webob.exc.HTTPBadRequest(explanation=msg)

            bulk_action = {
                '_op_type': action_type,
                '_id': document_id,
                '_index': index_name,
                '_type': document_type,
            }

            if script:
                data_field = 'params'
                bulk_action['script'] = script
            elif action_type == 'update':
                data_field = 'doc'
            else:
                data_field = '_source'

            bulk_action[data_field] = data

            output.append(bulk_action)
        return output

    def _get_query(self, context, query, doc_types):
        is_admin = context.is_admin
        if is_admin:
            query_params = {
                'query': {
                    'query': query
                }
            }
        else:
            filtered_query_list = []
            for plugin in self.plugins:
                try:
                    doc_type = plugin.obj.get_document_type()
                    rbac_filter = plugin.obj.get_rbac_filter(context)
                except Exception as e:
                    LOG.error(_LE("Failed to retrieve RBAC filters "
                                  "from search plugin "
                                  "%(ext)s: %(e)s") %
                              {'ext': plugin.name, 'e': e})

                if doc_type in doc_types:
                    filter_query = {
                        "query": query,
                        "filter": rbac_filter
                    }
                    filtered_query = {
                        'filtered': filter_query
                    }
                    filtered_query_list.append(filtered_query)

            query_params = {
                'query': {
                    'query': {
                        "bool": {
                            "should": filtered_query_list
                        },
                    }
                }
            }

        return query_params

    def search(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        query = body.pop('query', None)
        indices = body.pop('index', None)
        doc_types = body.pop('type', None)
        fields = body.pop('fields', None)
        offset = body.pop('offset', None)
        limit = body.pop('limit', None)
        highlight = body.pop('highlight', None)

        if not indices:
            indices = self._get_available_indices()
        elif not isinstance(indices, (list, tuple)):
            indices = [indices]

        if not doc_types:
            doc_types = self._get_available_types()
        elif not isinstance(doc_types, (list, tuple)):
            doc_types = [doc_types]

        query_params = self._get_query(request.context, query, doc_types)
        query_params['index'] = [self._validate_index(index)
                                 for index in indices]
        query_params['doc_type'] = [self._validate_doc_type(doc_type)
                                    for doc_type in doc_types]

        if fields is not None:
            query_params['fields'] = fields

        if offset is not None:
            query_params['offset'] = self._validate_offset(offset)

        if limit is not None:
            query_params['limit'] = self._validate_limit(limit)

        if highlight is not None:
            query_params['query']['highlight'] = highlight

        return query_params

    def index(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)

        default_index = body.pop('default_index', None)
        if default_index is not None:
            default_index = self._validate_index(default_index)

        default_type = body.pop('default_type', None)
        if default_type is not None:
            default_type = self._validate_doc_type(default_type)

        actions = self._validate_actions(body.pop('actions', None))
        if not all([default_index, default_type]):
            for action in actions:
                if not any([action['_index'], default_index]):
                    msg = (_("Action index is missing and no default "
                             "index has been set."))
                    raise webob.exc.HTTPBadRequest(explanation=msg)

                if not any([action['_type'], default_type]):
                    msg = (_("Action document type is missing and no default "
                             "type has been set."))
                    raise webob.exc.HTTPBadRequest(explanation=msg)

        query_params = {
            'default_index': default_index,
            'default_type': default_type,
            'actions': actions,
        }
        return query_params


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema

    def search(self, response, query_result):
        body = json.dumps(query_result, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def plugins_info(self, response, query_result):
        body = json.dumps(query_result, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def index(self, response, query_result):
        body = json.dumps(query_result, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'


def create_resource():
    """Search resource factory method"""
    plugins = utils.get_search_plugins()
    deserializer = RequestDeserializer(plugins)
    serializer = ResponseSerializer()
    controller = SearchController(plugins)
    return wsgi.Resource(controller, deserializer, serializer)
