# Copyright 2015 Hewlett-Packard Corporation
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

import mock
from oslo.serialization import jsonutils
import webob.exc

from glance.common import exception
from glance.common import utils
import glance.gateway
import glance.search
from glance.search.api.v0_1 import search as search
from glance.tests.unit import base
import glance.tests.unit.utils as unit_test_utils
import glance.tests.utils as test_utils


def _action_fixture(op_type, data, index=None, doc_type=None, _id=None,
                    **kwargs):
    action = {
        'action': op_type,
        'id': _id,
        'index': index,
        'type': doc_type,
        'data': data,
    }
    if kwargs:
        action.update(kwargs)

    return action


def _image_fixture(op_type, _id=None, index='glance', doc_type='image',
                   data=None, **kwargs):
    image_data = {
        'name': 'image-1',
        'disk_format': 'raw',
    }
    if data is not None:
        image_data.update(data)

    return _action_fixture(op_type, image_data, index, doc_type, _id, **kwargs)


class TestSearchController(base.IsolatedUnitTest):

    def setUp(self):
        super(TestSearchController, self).setUp()
        self.search_controller = search.SearchController()

    def test_search_all(self):
        request = unit_test_utils.get_fake_request()
        self.search_controller.search = mock.Mock(return_value="{}")

        query = {"match_all": {}}
        index = "glance"
        doc_type = "metadef"
        fields = None
        offset = 0
        limit = 10
        self.search_controller.search(
            request, query, index, doc_type, fields, offset, limit)
        self.search_controller.search.assert_called_once_with(
            request, query, index, doc_type, fields, offset, limit)

    def test_search_all_repo(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.search = mock.Mock(return_value="{}")
        query = {"match_all": {}}
        index = "glance"
        doc_type = "metadef"
        fields = []
        offset = 0
        limit = 10
        self.search_controller.search(
            request, query, index, doc_type, fields, offset, limit)
        repo.search.assert_called_once_with(
            index, doc_type, query, fields, offset, limit, True)

    def test_search_forbidden(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.search = mock.Mock(side_effect=exception.Forbidden)

        query = {"match_all": {}}
        index = "glance"
        doc_type = "metadef"
        fields = []
        offset = 0
        limit = 10

        self.assertRaises(
            webob.exc.HTTPForbidden, self.search_controller.search,
            request, query, index, doc_type, fields, offset, limit)

    def test_search_not_found(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.search = mock.Mock(side_effect=exception.NotFound)

        query = {"match_all": {}}
        index = "glance"
        doc_type = "metadef"
        fields = []
        offset = 0
        limit = 10

        self.assertRaises(
            webob.exc.HTTPNotFound, self.search_controller.search, request,
            query, index, doc_type, fields, offset, limit)

    def test_search_duplicate(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.search = mock.Mock(side_effect=exception.Duplicate)

        query = {"match_all": {}}
        index = "glance"
        doc_type = "metadef"
        fields = []
        offset = 0
        limit = 10

        self.assertRaises(
            webob.exc.HTTPConflict, self.search_controller.search, request,
            query, index, doc_type, fields, offset, limit)

    def test_search_internal_server_error(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.search = mock.Mock(side_effect=Exception)

        query = {"match_all": {}}
        index = "glance"
        doc_type = "metadef"
        fields = []
        offset = 0
        limit = 10

        self.assertRaises(
            webob.exc.HTTPInternalServerError, self.search_controller.search,
            request, query, index, doc_type, fields, offset, limit)

    def test_index_complete(self):
        request = unit_test_utils.get_fake_request()
        self.search_controller.index = mock.Mock(return_value="{}")
        actions = [{'action': 'create', 'index': 'myindex', 'id': 10,
                    'type': 'MyTest', 'data': '{"name": "MyName"}'}]
        default_index = 'glance'
        default_type = 'image'

        self.search_controller.index(
            request, actions, default_index, default_type)
        self.search_controller.index.assert_called_once_with(
            request, actions, default_index, default_type)

    def test_index_repo_complete(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.index = mock.Mock(return_value="{}")
        actions = [{'action': 'create', 'index': 'myindex', 'id': 10,
                    'type': 'MyTest', 'data': '{"name": "MyName"}'}]
        default_index = 'glance'
        default_type = 'image'

        self.search_controller.index(
            request, actions, default_index, default_type)
        repo.index.assert_called_once_with(
            default_index, default_type, actions)

    def test_index_repo_minimal(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.index = mock.Mock(return_value="{}")
        actions = [{'action': 'create', 'index': 'myindex', 'id': 10,
                    'type': 'MyTest', 'data': '{"name": "MyName"}'}]

        self.search_controller.index(request, actions)
        repo.index.assert_called_once_with(None, None, actions)

    def test_index_forbidden(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.index = mock.Mock(side_effect=exception.Forbidden)
        actions = [{'action': 'create', 'index': 'myindex', 'id': 10,
                    'type': 'MyTest', 'data': '{"name": "MyName"}'}]

        self.assertRaises(
            webob.exc.HTTPForbidden, self.search_controller.index,
            request, actions)

    def test_index_not_found(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.index = mock.Mock(side_effect=exception.NotFound)
        actions = [{'action': 'create', 'index': 'myindex', 'id': 10,
                    'type': 'MyTest', 'data': '{"name": "MyName"}'}]

        self.assertRaises(
            webob.exc.HTTPNotFound, self.search_controller.index,
            request, actions)

    def test_index_duplicate(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.index = mock.Mock(side_effect=exception.Duplicate)
        actions = [{'action': 'create', 'index': 'myindex', 'id': 10,
                    'type': 'MyTest', 'data': '{"name": "MyName"}'}]

        self.assertRaises(
            webob.exc.HTTPConflict, self.search_controller.index,
            request, actions)

    def test_index_exception(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.index = mock.Mock(side_effect=Exception)
        actions = [{'action': 'create', 'index': 'myindex', 'id': 10,
                    'type': 'MyTest', 'data': '{"name": "MyName"}'}]

        self.assertRaises(
            webob.exc.HTTPInternalServerError, self.search_controller.index,
            request, actions)

    def test_plugins_info(self):
        request = unit_test_utils.get_fake_request()
        self.search_controller.plugins_info = mock.Mock(return_value="{}")
        self.search_controller.plugins_info(request)
        self.search_controller.plugins_info.assert_called_once_with(request)

    def test_plugins_info_repo(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.plugins_info = mock.Mock(return_value="{}")
        self.search_controller.plugins_info(request)
        repo.plugins_info.assert_called_once_with()

    def test_plugins_info_forbidden(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.plugins_info = mock.Mock(side_effect=exception.Forbidden)

        self.assertRaises(
            webob.exc.HTTPForbidden, self.search_controller.plugins_info,
            request)

    def test_plugins_info_not_found(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.plugins_info = mock.Mock(side_effect=exception.NotFound)

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.search_controller.plugins_info, request)

    def test_plugins_info_internal_server_error(self):
        request = unit_test_utils.get_fake_request()
        repo = glance.search.CatalogSearchRepo
        repo.plugins_info = mock.Mock(side_effect=Exception)

        self.assertRaises(webob.exc.HTTPInternalServerError,
                          self.search_controller.plugins_info, request)


class TestSearchDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestSearchDeserializer, self).setUp()
        self.deserializer = search.RequestDeserializer(
            utils.get_search_plugins()
        )

    def test_single_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': 'glance',
        })

        output = self.deserializer.search(request)
        self.assertEqual(['glance'], output['index'])

    def test_single_doc_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': 'image',
        })

        output = self.deserializer.search(request)
        self.assertEqual(['image'], output['doc_type'])

    def test_empty_request(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({})

        output = self.deserializer.search(request)
        self.assertEqual(['glance'], output['index'])
        self.assertEqual(sorted(['image', 'metadef']),
                         sorted(output['doc_type']))

    def test_empty_request_admin(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({})
        request.context.is_admin = True

        output = self.deserializer.search(request)
        self.assertEqual(['glance'], output['index'])
        self.assertEqual(sorted(['image', 'metadef']),
                         sorted(output['doc_type']))

    def test_invalid_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': 'invalid',
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_invalid_doc_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': 'invalid',
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_forbidden_schema(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'schema': {},
        })

        self.assertRaises(webob.exc.HTTPForbidden, self.deserializer.search,
                          request)

    def test_forbidden_self(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'self': {},
        })

        self.assertRaises(webob.exc.HTTPForbidden, self.deserializer.search,
                          request)

    def test_fields_restriction(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['metadef'],
            'query': {'match_all': {}},
            'fields': ['description'],
        })

        output = self.deserializer.search(request)
        self.assertEqual(['glance'], output['index'])
        self.assertEqual(['metadef'], output['doc_type'])
        self.assertEqual(['description'], output['fields'])

    def test_highlight_fields(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['metadef'],
            'query': {'match_all': {}},
            'highlight': {'fields': {'name': {}}}
        })

        output = self.deserializer.search(request)
        self.assertEqual(['glance'], output['index'])
        self.assertEqual(['metadef'], output['doc_type'])
        self.assertEqual({'name': {}}, output['query']['highlight']['fields'])

    def test_invalid_limit(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['metadef'],
            'query': {'match_all': {}},
            'limit': 'invalid',
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_negative_limit(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['metadef'],
            'query': {'match_all': {}},
            'limit': -1,
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_invalid_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['metadef'],
            'query': {'match_all': {}},
            'offset': 'invalid',
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_negative_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['metadef'],
            'query': {'match_all': {}},
            'offset': -1,
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_limit_and_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['metadef'],
            'query': {'match_all': {}},
            'limit': 1,
            'offset': 2,
        })

        output = self.deserializer.search(request)
        self.assertEqual(['glance'], output['index'])
        self.assertEqual(['metadef'], output['doc_type'])
        self.assertEqual(1, output['limit'])
        self.assertEqual(2, output['offset'])


class TestIndexDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestIndexDeserializer, self).setUp()
        self.deserializer = search.RequestDeserializer(
            utils.get_search_plugins()
        )

    def test_empty_request(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({})

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_empty_actions(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'default_index': 'glance',
            'default_type': 'image',
            'actions': [],
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_missing_actions(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'default_index': 'glance',
            'default_type': 'image',
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_invalid_operation_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('invalid', '1')]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_invalid_default_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'default_index': 'invalid',
            'actions': [_image_fixture('create', '1')]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_invalid_default_doc_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'default_type': 'invalid',
            'actions': [_image_fixture('create', '1')]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_empty_operation_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('', '1')]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_missing_operation_type(self):
        action = _image_fixture('', '1')
        action.pop('action')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': 'glance',
                '_op_type': 'index',
                '_source': {'disk_format': 'raw', 'name': 'image-1'},
                '_type': 'image'
            }],
            'default_index': None,
            'default_type': None
        }
        self.assertEqual(expected, output)

    def test_create_single(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('create', '1')]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': 'glance',
                '_op_type': 'create',
                '_source': {'disk_format': 'raw', 'name': 'image-1'},
                '_type': 'image'
            }],
            'default_index': None,
            'default_type': None
        }
        self.assertEqual(expected, output)

    def test_create_multiple(self):
        actions = [
            _image_fixture('create', '1'),
            _image_fixture('create', '2', data={'name': 'image-2'}),
        ]

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': actions,
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [
                {
                    '_id': '1',
                    '_index': 'glance',
                    '_op_type': 'create',
                    '_source': {'disk_format': 'raw', 'name': 'image-1'},
                    '_type': 'image'
                },
                {
                    '_id': '2',
                    '_index': 'glance',
                    '_op_type': 'create',
                    '_source': {'disk_format': 'raw', 'name': 'image-2'},
                    '_type': 'image'
                },
            ],
            'default_index': None,
            'default_type': None
        }
        self.assertEqual(expected, output)

    def test_create_missing_data(self):
        action = _image_fixture('create', '1')
        action.pop('data')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_create_with_default_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'default_index': 'glance',
            'actions': [_image_fixture('create', '1', index=None)]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': None,
                '_op_type': 'create',
                '_source': {'disk_format': 'raw', 'name': 'image-1'},
                '_type': 'image'
            }],
            'default_index': 'glance',
            'default_type': None
        }
        self.assertEqual(expected, output)

    def test_create_with_default_doc_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'default_type': 'image',
            'actions': [_image_fixture('create', '1', doc_type=None)]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': 'glance',
                '_op_type': 'create',
                '_source': {'disk_format': 'raw', 'name': 'image-1'},
                '_type': None
            }],
            'default_index': None,
            'default_type': 'image'
        }
        self.assertEqual(expected, output)

    def test_create_with_default_index_and_doc_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'default_index': 'glance',
            'default_type': 'image',
            'actions': [_image_fixture('create', '1', index=None,
                                       doc_type=None)]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': None,
                '_op_type': 'create',
                '_source': {'disk_format': 'raw', 'name': 'image-1'},
                '_type': None
            }],
            'default_index': 'glance',
            'default_type': 'image'
        }
        self.assertEqual(expected, output)

    def test_create_missing_id(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('create')]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': None,
                '_index': 'glance',
                '_op_type': 'create',
                '_source': {'disk_format': 'raw', 'name': 'image-1'},
                '_type': 'image'
            }],
            'default_index': None,
            'default_type': None,
        }
        self.assertEqual(expected, output)

    def test_create_empty_id(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('create', '')]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '',
                '_index': 'glance',
                '_op_type': 'create',
                '_source': {'disk_format': 'raw', 'name': 'image-1'},
                '_type': 'image'
            }],
            'default_index': None,
            'default_type': None
        }
        self.assertEqual(expected, output)

    def test_create_invalid_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('create', index='invalid')]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_create_invalid_doc_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('create', doc_type='invalid')]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_create_missing_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('create', '1', index=None)]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_create_missing_doc_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('create', '1', doc_type=None)]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_update_missing_id(self):
        action = _image_fixture('update')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_update_missing_data(self):
        action = _image_fixture('update', '1')
        action.pop('data')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_update_using_data(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [_image_fixture('update', '1')]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': 'glance',
                '_op_type': 'update',
                '_type': 'image',
                'doc': {'disk_format': 'raw', 'name': 'image-1'}
            }],
            'default_index': None,
            'default_type': None
        }
        self.assertEqual(expected, output)

    def test_update_using_script(self):
        action = _image_fixture('update', '1', script='<sample script>')
        action.pop('data')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': 'glance',
                '_op_type': 'update',
                '_type': 'image',
                'params': {},
                'script': '<sample script>'
            }],
            'default_index': None,
            'default_type': None,
        }
        self.assertEqual(expected, output)

    def test_update_using_script_and_data(self):
        action = _image_fixture('update', '1', script='<sample script>')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': 'glance',
                '_op_type': 'update',
                '_type': 'image',
                'params': {'disk_format': 'raw', 'name': 'image-1'},
                'script': '<sample script>'
            }],
            'default_index': None,
            'default_type': None,
        }
        self.assertEqual(expected, output)

    def test_delete_missing_id(self):
        action = _image_fixture('delete')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.index,
                          request)

    def test_delete_single(self):
        action = _image_fixture('delete', '1')
        action.pop('data')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action]
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [{
                '_id': '1',
                '_index': 'glance',
                '_op_type': 'delete',
                '_source': {},
                '_type': 'image'
            }],
            'default_index': None,
            'default_type': None
        }
        self.assertEqual(expected, output)

    def test_delete_multiple(self):
        action_1 = _image_fixture('delete', '1')
        action_1.pop('data')
        action_2 = _image_fixture('delete', '2')
        action_2.pop('data')

        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'actions': [action_1, action_2],
        })

        output = self.deserializer.index(request)
        expected = {
            'actions': [
                {
                    '_id': '1',
                    '_index': 'glance',
                    '_op_type': 'delete',
                    '_source': {},
                    '_type': 'image'
                },
                {
                    '_id': '2',
                    '_index': 'glance',
                    '_op_type': 'delete',
                    '_source': {},
                    '_type': 'image'
                },
            ],
            'default_index': None,
            'default_type': None
        }
        self.assertEqual(expected, output)


class TestResponseSerializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestResponseSerializer, self).setUp()
        self.serializer = search.ResponseSerializer()

    def test_plugins_info(self):
        expected = {
            "plugins": [
                {
                    "index": "glance",
                    "type": "image"
                },
                {
                    "index": "glance",
                    "type": "metadef"
                }
            ]
        }

        request = webob.Request.blank('/v0.1/search')
        response = webob.Response(request=request)
        result = {
            "plugins": [
                {
                    "index": "glance",
                    "type": "image"
                },
                {
                    "index": "glance",
                    "type": "metadef"
                }
            ]
        }
        self.serializer.search(response, result)
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_search(self):
        expected = [{
            'id': '1',
            'name': 'image-1',
            'disk_format': 'raw',
        }]

        request = webob.Request.blank('/v0.1/search')
        response = webob.Response(request=request)
        result = [{
            'id': '1',
            'name': 'image-1',
            'disk_format': 'raw',
        }]
        self.serializer.search(response, result)
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_index(self):
        expected = {
            'success': '1',
            'failed': '0',
            'errors': [],
        }

        request = webob.Request.blank('/v0.1/index')
        response = webob.Response(request=request)
        result = {
            'success': '1',
            'failed': '0',
            'errors': [],
        }
        self.serializer.index(response, result)
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)
