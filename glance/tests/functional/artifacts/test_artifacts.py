# Copyright (c) 2015 Mirantis, Inc.
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

import unittest
import uuid

import mock
from oslo_serialization import jsonutils
import pkg_resources
import requests

from glance.api.v3 import artifacts
from glance.api.v3 import router
from glance.common.artifacts import definitions
from glance.common.artifacts import loader
from glance.common import wsgi
from glance.tests import functional


class Artifact(definitions.ArtifactType):
    __type_name__ = "WithProps"
    prop1 = definitions.String()
    prop2 = definitions.Integer()
    prop_list = definitions.Array(item_type=definitions.Integer())
    tuple_prop = definitions.Array(item_type=[definitions.Integer(),
                                              definitions.Boolean()])
    dict_prop = definitions.Dict(properties={
        "foo": definitions.String(),
        "bar_list": definitions.Array(definitions.Integer())})
    dict_prop_strval = definitions.Dict(properties=definitions.String())
    depends_on = definitions.ArtifactReference()
    depends_on_list = definitions.ArtifactReferenceList()


class ArtifactNoProps(definitions.ArtifactType):
    __type_name__ = "NoProp"


class ArtifactNoProps1(definitions.ArtifactType):
    __type_name__ = "NoProp"
    __type_version__ = "0.5"


class ArtifactWithBlob(definitions.ArtifactType):
    __type_name__ = "WithBlob"
    blob1 = definitions.BinaryObject()
    blob_list = definitions.BinaryObjectList()


def _create_resource():
    plugins = None
    mock_this = 'stevedore.extension.ExtensionManager._find_entry_points'
    with mock.patch(mock_this) as fep:
        path = 'glance.tests.functional.artifacts.test_artifacts'
        fep.return_value = [
            pkg_resources.EntryPoint.parse('WithProps=%s:Artifact' % path),
            pkg_resources.EntryPoint.parse(
                'NoProp=%s:ArtifactNoProps' % path),
            pkg_resources.EntryPoint.parse(
                'NoProp=%s:ArtifactNoProps1' % path),
            pkg_resources.EntryPoint.parse(
                'WithBlob=%s:ArtifactWithBlob' % path)
        ]
        plugins = loader.ArtifactsPluginLoader('glance.artifacts.types')
    deserializer = artifacts.RequestDeserializer(plugins=plugins)
    serializer = artifacts.ResponseSerializer()
    controller = artifacts.ArtifactsController(plugins=plugins)
    return wsgi.Resource(controller, deserializer, serializer)


class TestRouter(router.API):
    def _get_artifacts_resource(self):
        return _create_resource()


class TestArtifacts(functional.FunctionalTest):

    users = {
        'user1': {
            'id': str(uuid.uuid4()),
            'tenant_id': str(uuid.uuid4()),
            'token': str(uuid.uuid4()),
            'role': 'member'
        },
        'user2': {
            'id': str(uuid.uuid4()),
            'tenant_id': str(uuid.uuid4()),
            'token': str(uuid.uuid4()),
            'role': 'member'
        },
        'admin': {
            'id': str(uuid.uuid4()),
            'tenant_id': str(uuid.uuid4()),
            'token': str(uuid.uuid4()),
            'role': 'admin'
        }
    }

    def setUp(self):
        super(TestArtifacts, self).setUp()
        self._set_user('user1')
        self.api_server.deployment_flavor = 'noauth'
        self.start_servers(**self.__dict__.copy())

    def tearDown(self):
        self.stop_servers()
        self._reset_database(self.api_server.sql_connection)
        super(TestArtifacts, self).tearDown()

    def _url(self, path):
        return 'http://127.0.0.1:%d/v3/artifacts%s' % (self.api_port, path)

    def _set_user(self, username):
        if username not in self.users:
            raise KeyError
        self.current_user = username

    def _headers(self, custom_headers=None):
        base_headers = {
            'X-Identity-Status': 'Confirmed',
            'X-Auth-Token': self.users[self.current_user]['token'],
            'X-User-Id': self.users[self.current_user]['id'],
            'X-Tenant-Id': self.users[self.current_user]['tenant_id'],
            'X-Roles': self.users[self.current_user]['role'],
        }
        base_headers.update(custom_headers or {})
        return base_headers

    def start_servers(self, **kwargs):
        new_paste_conf_base = """[pipeline:glance-api]
pipeline = versionnegotiation gzip unauthenticated-context rootapp

[pipeline:glance-api-caching]
pipeline = versionnegotiation gzip unauthenticated-context cache rootapp

[pipeline:glance-api-cachemanagement]
pipeline =
    versionnegotiation
    gzip
    unauthenticated-context
    cache
    cache_manage
    rootapp

[pipeline:glance-api-fakeauth]
pipeline = versionnegotiation gzip fakeauth context rootapp

[pipeline:glance-api-noauth]
pipeline = versionnegotiation gzip context rootapp

[composite:rootapp]
paste.composite_factory = glance.api:root_app_factory
/: apiversions
/v1: apiv1app
/v2: apiv2app
/v3: apiv3app

[app:apiversions]
paste.app_factory = glance.api.versions:create_resource

[app:apiv1app]
paste.app_factory = glance.api.v1.router:API.factory

[app:apiv2app]
paste.app_factory = glance.api.v2.router:API.factory

[app:apiv3app]
paste.app_factory =
 glance.tests.functional.artifacts.test_artifacts:TestRouter.factory

[filter:versionnegotiation]
paste.filter_factory =
 glance.api.middleware.version_negotiation:VersionNegotiationFilter.factory

[filter:gzip]
paste.filter_factory = glance.api.middleware.gzip:GzipMiddleware.factory

[filter:cache]
paste.filter_factory = glance.api.middleware.cache:CacheFilter.factory

[filter:cache_manage]
paste.filter_factory =
 glance.api.middleware.cache_manage:CacheManageFilter.factory

[filter:context]
paste.filter_factory = glance.api.middleware.context:ContextMiddleware.factory

[filter:unauthenticated-context]
paste.filter_factory =
 glance.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:fakeauth]
paste.filter_factory = glance.tests.utils:FakeAuthMiddleware.factory
"""
        self.cleanup()
        self.api_server.paste_conf_base = new_paste_conf_base
        super(TestArtifacts, self).start_servers(**kwargs)

    def _create_artifact(self, type_name, type_version='1.0', data=None,
                         status=201):
        # create an artifact first
        artifact_data = data or {'name': 'artifact-1',
                                 'version': '12'}
        return self._check_artifact_post('/%s/v%s/drafts' % (type_name,
                                                             type_version),
                                         artifact_data, status=status)

    def _check_artifact_method(self, method, url, data=None, status=200,
                               headers=None):
        if not headers:
            headers = self._headers()
        else:
            headers = self._headers(headers)
        headers.setdefault("Content-Type", "application/json")
        if 'application/json' in headers['Content-Type']:
            data = jsonutils.dumps(data)
        response = getattr(requests, method)(self._url(url), headers=headers,
                                             data=data)
        self.assertEqual(status, response.status_code)
        if status >= 400:
            return response.text
        if "application/json" in response.headers["content-type"]:
            return jsonutils.loads(response.text)
        return response.text

    def _check_artifact_post(self, url, data, status=201,
                             headers={'Content-Type': 'application/json'}):
        return self._check_artifact_method("post", url, data, status=status,
                                           headers=headers)

    def _check_artifact_get(self, url, status=200):
        return self._check_artifact_method("get", url, status=status)

    def _check_artifact_delete(self, url, status=204):
        response = requests.delete(self._url(url), headers=self._headers())
        self.assertEqual(status, response.status_code)
        return response.text

    def _check_artifact_patch(self, url, data, status=200):
        return self._check_artifact_method("patch", url, data, status)

    def _check_artifact_put(self, url, data, status=200):
        return self._check_artifact_method("put", url, data, status=status)

    def test_list_any_artifacts(self):
        """Returns information about all draft artifacts with given endpoint"""
        self._create_artifact('noprop')
        artifacts = self._check_artifact_get('/noprop/drafts')["artifacts"]
        self.assertEqual(1, len(artifacts))

    def test_list_last_version(self):
        """/artifacts/endpoint == /artifacts/endpoint/all-versions"""
        self._create_artifact('noprop')
        artifacts = self._check_artifact_get('/noprop/drafts')["artifacts"]
        self.assertEqual(1, len(artifacts))
        # the same result can be achieved if asked for artifact with
        # type_version=last version
        artifacts_precise = self._check_artifact_get(
            '/noprop/v1.0/drafts')["artifacts"]
        self.assertEqual(artifacts, artifacts_precise)

    def test_list_artifacts_by_state(self):
        """Returns last version of artifacts with given state"""
        self._create_artifact('noprop')
        creating_state = self._check_artifact_get(
            '/noprop/drafts')["artifacts"]
        self.assertEqual(1, len(creating_state))
        # no active [/type_name/active == /type_name]
        active_state = self._check_artifact_get('/noprop')["artifacts"]
        self.assertEqual(0, len(active_state))

    def test_list_artifacts_with_version(self):
        """Supplying precise artifact version does not break anything"""
        self._create_artifact('noprop')
        list_creating = self._check_artifact_get(
            '/noprop/v1.0/drafts')["artifacts"]
        self.assertEqual(1, len(list_creating))
        bad_version = self._check_artifact_get('/noprop/v1.0bad',
                                               status=400)
        self.assertIn("Invalid version string: u'1.0bad'", bad_version)

    def test_list_artifacts_with_pagination(self):
        """List artifacts with pagination"""
        # create artifacts
        art1 = {'name': 'artifact-1',
                'version': '12'}
        art2 = {'name': 'artifact-2',
                'version': '12'}
        self._create_artifact('noprop', data=art1)
        self._create_artifact('noprop', data=art2)
        # sorting is desc by default
        first_page = self._check_artifact_get(
            '/noprop/drafts?limit=1&sort=name')
        # check the first artifacts has returned correctly
        self.assertEqual(1, len(first_page["artifacts"]))
        self.assertEqual("artifact-2", first_page["artifacts"][0]["name"])
        self.assertIn("next", first_page)
        # check the second page
        second_page_url = first_page["next"].split("artifacts", 1)[1]
        second_page = self._check_artifact_get(second_page_url)
        self.assertIn("next", second_page)
        self.assertEqual(1, len(second_page["artifacts"]))
        self.assertEqual("artifact-1", second_page["artifacts"][0]["name"])
        # check that the latest item is empty
        last_page_url = second_page["next"].split("artifacts", 1)[1]
        last_page = self._check_artifact_get(last_page_url)
        self.assertEqual(0, len(last_page["artifacts"]))
        self.assertNotIn("next", last_page)

    def test_get_artifact_by_id_any_version(self):
        data = self._create_artifact('noprop')
        artifact_id = data['id']
        artifacts = self._check_artifact_get(
            '/noprop/%s' % artifact_id)
        self.assertEqual(artifact_id, artifacts['id'])

    def test_list_artifact_no_such_version(self):
        """Version filtering should be applied for existing plugins.

        An attempt to retrieve an artifact out of existing plugin but with
        a wrong version should result in
        400 BadRequest 'No such plugin has been loaded'
        """
        msg = self._check_artifact_get('/noprop/v0.0.9', 400)
        self.assertIn("No plugin for 'noprop v 0.0.9' has been loaded",
                      msg)

    def test_get_artifact_by_id(self):
        data = self._create_artifact('noprop')
        artifact_id = data['id']
        artifacts = self._check_artifact_get(
            '/noprop/%s' % artifact_id)
        self.assertEqual(artifact_id, artifacts['id'])
        # the same result can be achieved if asked for artifact with
        # type_version=last version
        artifacts_precise = self._check_artifact_get(
            '/noprop/v1.0/%s' % artifact_id)
        self.assertEqual(artifacts, artifacts_precise)

    def test_get_artifact_basic_show_level(self):
        no_prop_art = self._create_artifact('noprop')
        art = self._create_artifact(
            'withprops',
            data={"name": "name", "version": "42",
                  "depends_on": no_prop_art['id']})
        self.assertEqual(no_prop_art['id'], art['depends_on']['id'])
        self.assertEqual(no_prop_art['name'], art['depends_on']['name'])

        artifact_id = art['id']
        artifact = self._check_artifact_get(
            '/withprops/%s?show_level=basic' % artifact_id)
        self.assertEqual(artifact_id, artifact['id'])
        self.assertIsNone(artifact['depends_on'])

    def test_get_artifact_none_show_level(self):
        """Create an artifact (with two deployer-defined properties)"""
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'tags': ['gagaga', 'sesese'],
                         'prop1': 'Arthur Dent',
                         'prop2': 42}
        art = self._check_artifact_post('/withprops/v1.0/drafts',
                                        artifact_data)
        expected_artifact = {
            'state': 'creating',
            'name': 'artifact-1',
            'version': '12.0.0',
            'tags': ['gagaga', 'sesese'],
            'visibility': 'private',
            'type_name': 'WithProps',
            'type_version': '1.0',
            'prop1': 'Arthur Dent',
            'prop2': 42
        }
        for key, value in expected_artifact.items():
            self.assertEqual(art[key], value, key)

        artifact_id = art['id']
        artifact = self._check_artifact_get(
            '/withprops/%s?show_level=none' % artifact_id)
        self.assertEqual(artifact_id, artifact['id'])
        self.assertIsNone(artifact['prop1'])
        self.assertIsNone(artifact['prop2'])

    def test_get_artifact_invalid_show_level(self):
        no_prop_art = self._create_artifact('noprop')
        art = self._create_artifact(
            'withprops',
            data={"name": "name", "version": "42",
                  "depends_on": no_prop_art['id']})
        self.assertEqual(no_prop_art['id'], art['depends_on']['id'])
        self.assertEqual(no_prop_art['name'], art['depends_on']['name'])

        artifact_id = art['id']
        # 'hui' is invalid show level
        self._check_artifact_get(
            '/noprop/%s?show_level=yoba' % artifact_id, status=400)

    def test_get_artifact_no_such_id(self):
        msg = self._check_artifact_get(
            '/noprop/%s' % str(uuid.uuid4()), status=404)
        self.assertIn('No artifact found with ID', msg)

    def test_get_artifact_present_id_wrong_type(self):
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'prop1': '12',
                         'prop2': 12}
        art1 = self._create_artifact('withprops', data=artifact_data)
        art2 = self._create_artifact('noprop')
        # ok id and type_name but bad type_version should result in 404
        self._check_artifact_get('/noprop/v0.5/%s' % str(art2['id']),
                                 status=404)
        # try to access art2 by supplying art1.type and art2.id
        self._check_artifact_get('/withprops/%s' % str(art2['id']),
                                 status=404)
        self._check_artifact_get('/noprop/%s' % str(art1['id']), status=404)

    def test_delete_artifact(self):
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'prop1': '12',
                         'prop2': 12}
        art1 = self._create_artifact('withprops', data=artifact_data)
        self._check_artifact_delete('/withprops/v1.0/%s' % art1['id'])
        art1_deleted = self._check_artifact_get('/withprops/%s' % art1['id'],
                                                status=404)
        self.assertIn('No artifact found with ID', art1_deleted)

    def test_delete_artifact_no_such_id(self):
        self._check_artifact_delete('/noprop/v1/%s' % str(uuid.uuid4()),
                                    status=404)

    @unittest.skip("Test is unstable")
    def test_delete_artifact_with_dependency(self):
        # make sure that artifact can't be deleted if it has some dependencies
        # still not deleted
        art = self._create_artifact('withprops')
        no_prop_art = self._create_artifact('noprop')
        art_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % art['id'],
            data=[{'value': no_prop_art['id'],
                   'op': 'replace',
                   'path': '/depends_on'},
                  {'value': [no_prop_art['id']],
                   'op': 'add',
                   'path': '/depends_on_list'}])
        self.assertEqual(no_prop_art['id'], art_updated['depends_on']['id'])
        self.assertEqual(1, len(art_updated['depends_on_list']))
        # try to delete an artifact prior to its dependency
        res = self._check_artifact_delete('/withprops/v1/%s' % art['id'],
                                          status=400)
        self.assertIn(
            "Dependency property 'depends_on' has to be deleted first", res)
        # delete a dependency
        art_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % art['id'],
            data=[{'op': 'remove', 'path': '/depends_on'}])
        # try to delete prior to deleting artifact_list dependencies
        res = self._check_artifact_delete('/withprops/v1/%s' % art['id'],
                                          status=400)
        self.assertIn(
            "Dependency property 'depends_on_list' has to be deleted first",
            res)
        art_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % art['id'],
            data=[{'op': 'remove', 'path': '/depends_on_list'}])
        # delete dependency list
        self._check_artifact_delete('/withprops/v1/%s' % art['id'])

    def test_delete_artifact_with_blob(self):
        # Upload some data to an artifact
        art = self._create_artifact('withblob')
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        self._check_artifact_post('/withblob/v1/%s/blob1' % art['id'],
                                  headers=headers,
                                  data='ZZZZZ', status=200)
        self._check_artifact_delete('/withblob/v1/%s' % art['id'])

    def test_update_array_property_by_replace_op(self):
        art = self._create_artifact('withprops', data={'name': 'some art',
                                                       'version': '4.2'})
        self.assertEqual('some art', art['name'])
        data = [{'op': 'replace', 'value': [1, 2, 3], 'path': '/prop_list'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s' %
                                                 art['id'],
                                                 data=data)
        self.assertEqual([1, 2, 3], art_updated['prop_list'])
        # now try to change first element of the list
        data_change_first = [{'op': 'replace', 'value': 42,
                              'path': '/prop_list/1'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s' %
                                                 art['id'],
                                                 data=data_change_first)
        self.assertEqual([1, 42, 3], art_updated['prop_list'])
        # replace last element
        data_change_last = [{'op': 'replace', 'value': 24,
                             'path': '/prop_list/-'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s' %
                                                 art['id'],
                                                 data=data_change_last)
        self.assertEqual([1, 42, 24], art_updated['prop_list'])

    def test_update_dict_property_by_replace_op(self):
        art = self._create_artifact(
            'withprops',
            data={'name': 'some art',
                  'version': '4.2',
                  'dict_prop': {'foo': "Fenchurch", 'bar_list': [42, 42]}})
        self.assertEqual({'foo': "Fenchurch", 'bar_list': [42, 42]},
                         art['dict_prop'])
        data = [{'op': 'replace', 'value': 24,
                 'path': '/dict_prop/bar_list/0'},
                {'op': 'replace', 'value': 'cello lesson',
                 'path': '/dict_prop/foo'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertEqual({'foo': 'cello lesson', 'bar_list': [24, 42]},
                         art_updated['dict_prop'])

    def test_update_empty_dict_property_by_replace_op(self):
        art = self._create_artifact('withprops')
        self.assertIsNone(art['dict_prop'])
        data = [{'op': 'replace', 'value': "don't panic",
                 'path': '/dict_prop/foo'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data, status=400)
        self.assertIn("The provided path 'dict_prop/foo' is invalid",
                      art_updated)

    def test_update_empty_dict_property_by_remove_op(self):
        art = self._create_artifact('withprops')
        self.assertIsNone(art['dict_prop'])
        data = [{'op': 'remove', 'path': '/dict_prop/bar_list'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data, status=400)
        self.assertIn("The provided path 'dict_prop/bar_list' is invalid",
                      art_updated)

    def test_update_dict_property_by_remove_op(self):
        art = self._create_artifact(
            'withprops',
            data={'name': 'some art', 'version': '4.2',
                  'dict_prop': {'foo': "Fenchurch", 'bar_list': [42, 42]}})
        self.assertEqual({'foo': 'Fenchurch', 'bar_list': [42, 42]},
                         art['dict_prop'])
        data = [{'op': 'remove', 'path': '/dict_prop/foo'},
                {'op': 'remove', 'path': '/dict_prop/bar_list/1'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertEqual({'bar_list': [42]}, art_updated['dict_prop'])
        # now delete the whole dict
        data = [{'op': 'remove', 'path': '/dict_prop'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertIsNone(art_updated['dict_prop'])

    @unittest.skip("Skipping due to a know bug")
    def test_update_dict_property_change_values(self):
        art = self._create_artifact(
            'withprops', data={'name': 'some art', 'version': '4.2',
                               'dict_prop_strval':
                               {'foo': 'Fenchurch', 'bar': 'no value'}})
        self.assertEqual({'foo': 'Fenchurch', 'bar': 'no value'},
                         art['dict_prop_strval'])
        new_data = [{'op': 'replace', 'path': '/dict_prop_strval',
                     'value': {'new-foo': 'Arthur Dent'}}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=new_data)
        self.assertEqual({'new-foo': 'Arthur Dent'},
                         art_updated['dict_prop_strval'])

    def test_update_array_property_by_remove_op(self):
        art = self._create_artifact(
            'withprops', data={'name': 'some art',
                               'version': '4.2',
                               'prop_list': [1, 2, 3]})
        self.assertEqual([1, 2, 3], art['prop_list'])
        data = [{'op': 'remove', 'path': '/prop_list/0'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertEqual([2, 3], art_updated['prop_list'])
        # remove last element
        data = [{'op': 'remove', 'path': '/prop_list/-'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertEqual([2], art_updated['prop_list'])
        # now delete the whole array
        data = [{'op': 'remove', 'path': '/prop_list'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertIsNone(art_updated['prop_list'])

    def test_update_array_property_by_add_op(self):
        art = self._create_artifact(
            'withprops', data={'name': 'some art',
                               'version': '4.2'})
        self.assertIsNone(art['prop_list'])
        data = [{'op': 'add', 'path': '/prop_list', 'value': [2, 12, 0, 6]}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'], data=data)
        self.assertEqual([2, 12, 0, 6], art_updated['prop_list'])
        data = [{'op': 'add', 'path': '/prop_list/2', 'value': 85}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'], data=data)
        self.assertEqual([2, 12, 85, 0, 6], art_updated['prop_list'])
        # add where path='/array/-' means append to the end
        data = [{'op': 'add', 'path': '/prop_list/-', 'value': 7}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'], data=data)
        self.assertEqual([2, 12, 85, 0, 6, 7], art_updated['prop_list'])
        # an attempt to add an element to nonexistent position should
        # result in 400
        self.assertEqual(6, len(art_updated['prop_list']))
        bad_index_data = [{'op': 'add', 'path': '/prop_list/11',
                           'value': 42}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=bad_index_data,
                                                 status=400)
        self.assertIn("The provided path 'prop_list/11' is invalid",
                      art_updated)

    def test_update_dict_property_by_add_op(self):
        art = self._create_artifact("withprops")
        self.assertIsNone(art['dict_prop'])
        data = [{'op': 'add', 'path': '/dict_prop/foo', 'value': "some value"}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertEqual({"foo": "some value"}, art_updated['dict_prop'])

    def test_update_empty_array_property_by_add_op(self):
        """Test jsonpatch add.

        According to RFC 6902:
        * if the array is empty, '/array/0' is a valid path
        """
        create_data = {'name': 'new artifact',
                       'version': '4.2'}
        art = self._create_artifact('withprops', data=create_data)
        self.assertIsNone(art['prop_list'])
        data = [{'op': 'add', 'path': '/prop_list/0', 'value': 3}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertEqual([3], art_updated['prop_list'])

    def test_update_tuple_property_by_index(self):
        art = self._create_artifact(
            'withprops', data={'name': 'some art',
                               'version': '4.2',
                               'tuple_prop': [1, False]})
        self.assertEqual([1, False], art['tuple_prop'])
        data = [{'op': 'replace', 'value': True,
                 'path': '/tuple_prop/1'},
                {'op': 'replace', 'value': 2,
                 'path': '/tuple_prop/0'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertEqual([2, True], art_updated['tuple_prop'])

    def test_update_artifact(self):
        art = self._create_artifact('noprop')
        self.assertEqual('artifact-1', art['name'])
        art_updated = self._check_artifact_patch(
            '/noprop/v1/%s' % art['id'],
            data=[{'op': 'replace', 'value': '0.0.9', 'path': '/version'}])
        self.assertEqual('0.0.9', art_updated['version'])

    def test_update_artifact_properties(self):
        art = self._create_artifact('withprops')
        for prop in ['prop1', 'prop2']:
            self.assertIsNone(art[prop])
            data = [{'op': 'replace', 'value': 'some value',
                     'path': '/prop1'}]
            art_updated = self._check_artifact_patch(
                '/withprops/v1/%s' % art['id'], data=data)
            self.assertEqual('some value', art_updated['prop1'])

    def test_update_remove_non_existent_artifact_properties(self):
        art = self._create_artifact('withprops')
        for prop in ['prop1', 'prop2']:
            self.assertIsNone(art[prop])
            data = [{'op': 'remove', 'value': 'some value',
                     'path': '/non-existent-path/and-another'}]
            art_updated = self._check_artifact_patch(
                '/withprops/v1/%s' % art['id'], data=data, status=400)
            self.assertIn('Artifact has no property', art_updated)

    def test_update_replace_non_existent_artifact_properties(self):
        art = self._create_artifact('withprops')
        for prop in ['prop1', 'prop2']:
            self.assertIsNone(art[prop])
            data = [{'op': 'replace', 'value': 'some value',
                     'path': '/non-existent-path/and-another'}]
            art_updated = self._check_artifact_patch(
                '/withprops/v1/%s' % art['id'], data=data, status=400)
            self.assertIn('Artifact has no property', art_updated)

    def test_update_artifact_remove_property(self):
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'tags': ['gagaga', 'sesese'],
                         'prop1': 'Arthur Dent',
                         'prop2': 42}
        art = self._create_artifact('withprops', data=artifact_data)
        data = [{'op': 'remove', 'path': '/prop1'}]
        art_updated = self._check_artifact_patch('/withprops/v1/%s'
                                                 % art['id'],
                                                 data=data)
        self.assertIsNone(art_updated['prop1'])
        self.assertEqual(42, art_updated['prop2'])

    def test_update_wrong_property_type(self):
        art = self._create_artifact('withprops')
        for prop in ['prop2', 'prop2']:
            self.assertIsNone(art[prop])
        data = [{'op': 'replace', 'value': 123, 'path': '/prop1'}]
        art_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % art['id'], data=data, status=400)
        self.assertIn("Property 'prop1' may not have value '123'", art_updated)

    def test_update_multiple_properties(self):
        with_prop_art = self._create_artifact('withprops')
        data = [{'op': 'replace',
                 'path': '/prop1',
                 'value': 'some value'},
                {'op': 'replace',
                 'path': '/prop2',
                 'value': 42}]
        updated = self._check_artifact_patch(
            '/withprops/v1/%s' % with_prop_art['id'], data=data)
        self.assertEqual('some value', updated['prop1'])
        self.assertEqual(42, updated['prop2'])

    def test_create_artifact_with_dependency(self):
        no_prop_art = self._create_artifact('noprop')
        art = self._create_artifact(
            'withprops',
            data={"name": "name", "version": "42",
                  "depends_on": no_prop_art['id']})
        self.assertEqual(no_prop_art['id'], art['depends_on']['id'])
        self.assertEqual(no_prop_art['name'], art['depends_on']['name'])

    def test_create_artifact_dependency_list(self):
        no_prop_art1 = self._create_artifact('noprop')
        no_prop_art2 = self._create_artifact('noprop')
        art = self._create_artifact(
            'withprops',
            data={"name": "name", "version": "42",
                  "depends_on_list": [no_prop_art1['id'], no_prop_art2['id']]})
        self.assertEqual(2, len(art['depends_on_list']))
        self.assertEqual([no_prop_art1['id'], no_prop_art2['id']],
                         map(lambda x: x['id'], art['depends_on_list']))

    def test_create_dependency_list_same_id(self):
        no_prop_art = self._create_artifact('noprop')
        res = self._create_artifact(
            'withprops',
            data={"name": "name", "version": "42",
                  "depends_on_list": [no_prop_art['id'],
                                      no_prop_art['id']]}, status=400)
        self.assertIn("Items have to be unique", res)

    def test_create_artifact_bad_dependency_format(self):
        """Invalid dependencies creation.

        Dependencies should be passed:
        * as a list of ids if param is an ArtifactReferenceList
        * as an id if param is an ArtifactReference
        """
        no_prop_art = self._create_artifact('noprop')
        art = self._check_artifact_post(
            '/withprops/v1/drafts',
            {"name": "name", "version": "42",
             "depends_on": [no_prop_art['id']]}, status=400)
        self.assertIn('Not a valid value type', art)
        art = self._check_artifact_post(
            '/withprops/v1.0/drafts',
            {"name": "name", "version": "42",
             "depends_on_list": no_prop_art['id']}, status=400)
        self.assertIn('object is not iterable', art)

    def test_update_dependency(self):
        no_prop_art = self._create_artifact('noprop')
        no_prop_art1 = self._create_artifact('noprop')
        with_prop_art = self._create_artifact('withprops')
        data = [{'op': 'replace',
                 'path': '/depends_on',
                 'value': no_prop_art['id']}]
        updated = self._check_artifact_patch(
            '/withprops/v1/%s' % with_prop_art['id'], data=data)
        self.assertEqual(no_prop_art['id'], updated['depends_on']['id'])
        self.assertEqual(no_prop_art['name'], updated['depends_on']['name'])
        data = [{'op': 'replace',
                 'path': '/depends_on',
                 'value': no_prop_art1['id']}]
        # update again and make sure it changes
        updated = self._check_artifact_patch(
            '/withprops/v1/%s' % with_prop_art['id'], data=data)
        self.assertEqual(no_prop_art1['id'], updated['depends_on']['id'])
        self.assertEqual(no_prop_art1['name'], updated['depends_on']['name'])

    def test_update_dependency_circular_reference(self):
        with_prop_art = self._create_artifact('withprops')
        data = [{'op': 'replace',
                 'path': '/depends_on',
                 'value': [with_prop_art['id']]}]
        not_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % with_prop_art['id'], data=data, status=400)
        self.assertIn('Artifact with a circular dependency can not be created',
                      not_updated)

    def test_publish_artifact(self):
        art = self._create_artifact('withprops')
        # now create dependency
        no_prop_art = self._create_artifact('noprop')
        art_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % art['id'],
            data=[{'value': no_prop_art['id'],
                   'op': 'replace',
                   'path': '/depends_on'}])
        self.assertTrue(art_updated['depends_on'] != [])
        # artifact can't be published if any dependency is in non-active state
        res = self._check_artifact_post(
            '/withprops/v1/%s/publish' % art['id'], {}, status=400)
        self.assertIn("Not all dependencies are in 'active' state", res)
        # after you publish the dependency -> artifact can be published
        dep_published = self._check_artifact_post(
            '/noprop/v1/%s/publish' % no_prop_art['id'], {}, status=200)
        self.assertEqual('active', dep_published['state'])
        art_published = self._check_artifact_post(
            '/withprops/v1.0/%s/publish' % art['id'], {}, status=200)
        self.assertEqual('active', art_published['state'])

    def test_no_mutable_change_in_published_state(self):
        art = self._create_artifact('withprops')
        no_prop_art = self._create_artifact('noprop')
        no_prop_other = self._create_artifact('noprop')
        art_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % art['id'],
            data=[{'value': no_prop_art['id'],
                   'op': 'replace',
                   'path': '/depends_on'}])
        self.assertEqual(no_prop_art['id'], art_updated['depends_on']['id'])
        # now change dependency to some other artifact
        art_updated = self._check_artifact_patch(
            '/withprops/v1/%s' % art['id'],
            data=[{'value': no_prop_other['id'],
                   'op': 'replace',
                   'path': '/depends_on'}])
        self.assertEqual(no_prop_other['id'], art_updated['depends_on']['id'])
        # publish dependency
        dep_published = self._check_artifact_post(
            '/noprop/v1/%s/publish' % no_prop_other['id'], {}, status=200)
        self.assertEqual('active', dep_published['state'])
        # publish artifact
        art_published = self._check_artifact_post(
            '/withprops/v1.0/%s/publish' % art['id'], {}, status=200)
        self.assertEqual('active', art_published['state'])
        # try to change dependency, should fail as already published
        res = self._check_artifact_patch(
            '/withprops/v1/%s' % art_published['id'],
            data=[{'op': 'remove', 'path': '/depends_on'}], status=400)
        self.assertIn('Attempt to set value of immutable property', res)

    def test_create_artifact_empty_body(self):
        self._check_artifact_post('/noprop/v1.0/drafts', {}, 400)

    def test_create_artifact_insufficient_arguments(self):
        self._check_artifact_post('/noprop/v1.0/drafts',
                                  {'name': 'some name, no version'},
                                  status=400)

    def test_create_artifact_no_such_version(self):
        """Creation impossible without specifying a correct version.

        An attempt to create an artifact out of existing plugin but with
        a wrong version should result in
        400 BadRequest 'No such plugin has been loaded'
        """
        # make sure there is no such artifact noprop
        self._check_artifact_get('/noprop/v0.0.9', 400)
        artifact_data = {'name': 'artifact-1',
                         'version': '12'}
        msg = self._check_artifact_post('/noprop/v0.0.9/drafts',
                                        artifact_data,
                                        status=400)
        self.assertIn("No plugin for 'noprop v 0.0.9' has been loaded",
                      msg)

    def test_create_artifact_no_type_version_specified(self):
        """Creation impossible without specifying a version.

        It should not be possible to create an artifact out of existing plugin
        without specifying any version
        """
        artifact_data = {'name': 'artifact-1',
                         'version': '12'}
        self._check_artifact_post('/noprop/drafts', artifact_data, 404)

    def test_create_artifact_no_properties(self):
        """Create an artifact with minimum parameters"""
        artifact_data = {'name': 'artifact-1',
                         'version': '12'}
        artifact = self._check_artifact_post('/withprops/v1.0/drafts',
                                             artifact_data)
        # verify that all fields have the values expected
        expected_artifact = {
            'state': 'creating',
            'name': 'artifact-1',
            'version': '12.0.0',
            'tags': [],
            'visibility': 'private',
            'type_name': 'WithProps',
            'type_version': '1.0',
            'prop1': None,
            'prop2': None
        }
        for key, value in expected_artifact.items():
            self.assertEqual(artifact[key], value, key)

    def test_create_artifact_with_properties(self):
        """Create an artifact (with two deployer-defined properties)"""
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'tags': ['gagaga', 'sesese'],
                         'prop1': 'Arthur Dent',
                         'prop2': 42}
        artifact = self._check_artifact_post('/withprops/v1.0/drafts',
                                             artifact_data)
        expected_artifact = {
            'state': 'creating',
            'name': 'artifact-1',
            'version': '12.0.0',
            'tags': ['gagaga', 'sesese'],
            'visibility': 'private',
            'type_name': 'WithProps',
            'type_version': '1.0',
            'prop1': 'Arthur Dent',
            'prop2': 42
        }
        for key, value in expected_artifact.items():
            self.assertEqual(artifact[key], value, key)

    def test_create_artifact_not_all_properties(self):
        """Create artifact with minimal properties.

        Checks that it is possible to create an artifact by passing all
        required properties but omitting some not required
        """
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'visibility': 'private',
                         'tags': ['gagaga', 'sesese'],
                         'prop1': 'i am ok'}
        artifact = self._check_artifact_post('/withprops/v1.0/drafts',
                                             artifact_data)
        expected_artifact = {
            'state': 'creating',
            'name': 'artifact-1',
            'version': '12.0.0',
            'tags': ['gagaga', 'sesese'],
            'visibility': 'private',
            'type_name': 'WithProps',
            'type_version': '1.0',
            'prop1': 'i am ok',
            'prop2': None}
        for key, value in expected_artifact.items():
            self.assertEqual(artifact[key], value, key)
        # now check creation with no properties specified
        for prop in ['prop1', 'prop2']:
            artifact_data.pop(prop, '')
        artifact = self._check_artifact_post('/withprops/v1.0/drafts',
                                             artifact_data)
        for prop in ['prop1', 'prop2']:
            self.assertIsNone(artifact[prop])

    def test_create_artifact_invalid_properties(self):
        """Any attempt to pass invalid properties should result in 400"""
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'prop1': 1}
        res = self._check_artifact_post('/withprops/v1.0/drafts',
                                        artifact_data,
                                        status=400)
        self.assertIn("Property 'prop1' may not have value '1'", res)
        artifact_data.pop('prop1')
        artifact_data['nosuchprop'] = "Random"
        res = self._check_artifact_post('/withprops/v1.0/drafts',
                                        artifact_data,
                                        status=400)
        self.assertIn("Artifact has no property nosuchprop", res)

    def test_upload_file(self):
        # Upload some data to an artifact
        art = self._create_artifact('withblob')
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        self._check_artifact_post('/withblob/v1/%s/blob1' % art['id'],
                                  headers=headers,
                                  data='ZZZZZ', status=200)

    def test_upload_list_files(self):
        art = self._create_artifact('withblob')
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        self._check_artifact_post('/withblob/v1/%s/blob_list' % art['id'],
                                  headers=headers,
                                  data='ZZZZZ', status=200)
        self._check_artifact_post('/withblob/v1/%s/blob_list' % art['id'],
                                  headers=headers,
                                  data='YYYYY', status=200)

    def test_download_file(self):
        # Download some data from an artifact
        art = self._create_artifact('withblob')
        artifact_id = art['id']
        headers = self._headers({'Content-Type': 'application/octet-stream'})
        self._check_artifact_post('/withblob/v1/%s/blob1' % art['id'],
                                  headers=headers,
                                  data='ZZZZZ', status=200)

        art = self._check_artifact_get('/withblob/%s' % artifact_id)
        self.assertEqual(artifact_id, art['id'])
        self.assertIn('download_link', art['blob1'])

        data = self._check_artifact_get(
            '/withblob/%s/blob1/download' % art['id'])
        self.assertEqual('ZZZZZ', data)

    def test_file_w_unknown_size(self):
        # Upload and download data provided by an iterator, thus without
        # knowing the length in advance
        art = self._create_artifact('withblob')
        artifact_id = art['id']

        def iterate_string(val):
            for char in val:
                yield char

        headers = self._headers({'Content-Type': 'application/octet-stream'})
        self._check_artifact_post('/withblob/v1/%s/blob1' % art['id'],
                                  headers=headers,
                                  data=iterate_string('ZZZZZ'), status=200)

        art = self._check_artifact_get('/withblob/%s' % artifact_id)
        self.assertEqual(artifact_id, art['id'])
        self.assertIn('download_link', art['blob1'])

        data = self._check_artifact_get(
            '/withblob/%s/blob1/download' % art['id'])
        self.assertEqual('ZZZZZ', data)

    def test_limit(self):
        artifact_data = {'name': 'artifact-1',
                         'version': '12'}
        self._check_artifact_post('/withprops/v1/drafts',
                                  artifact_data)
        artifact_data = {'name': 'artifact-1',
                         'version': '13'}
        self._check_artifact_post('/withprops/v1/drafts',
                                  artifact_data)
        result = self._check_artifact_get('/withprops/v1/drafts')
        self.assertEqual(2, len(result["artifacts"]))
        result = self._check_artifact_get('/withprops/v1/drafts?limit=1')
        self.assertEqual(1, len(result["artifacts"]))

    def _check_sorting_order(self, expected, actual):
        for e, a in zip(expected, actual):
            self.assertEqual(e['name'], a['name'])
            self.assertEqual(e['version'], a['version'])
            self.assertEqual(e['prop1'], a['prop1'])

    def test_sort(self):
        artifact_data = {'name': 'artifact-1',
                         'version': '12',
                         'prop1': 'lala'}
        art1 = self._check_artifact_post('/withprops/v1.0/drafts',
                                         artifact_data)
        artifact_data = {'name': 'artifact-2',
                         'version': '13',
                         'prop1': 'lala'}
        art2 = self._check_artifact_post('/withprops/v1.0/drafts',
                                         artifact_data)
        artifact_data = {'name': 'artifact-3',
                         'version': '13',
                         'prop1': 'tutu'}
        art3 = self._check_artifact_post('/withprops/v1.0/drafts',
                                         artifact_data)
        artifact_data = {'name': 'artifact-4',
                         'version': '13',
                         'prop1': 'hyhy'}
        art4 = self._check_artifact_post('/withprops/v1.0/drafts',
                                         artifact_data)
        artifact_data = {'name': 'artifact-5',
                         'version': '13',
                         'prop1': 'bebe'}
        art5 = self._check_artifact_post('/withprops/v1.0/drafts',
                                         artifact_data)

        result = self._check_artifact_get(
            '/withprops/v1.0/drafts?sort=name')["artifacts"]
        self.assertEqual(5, len(result))

        # default direction is 'desc'
        expected = [art5, art4, art3, art2, art1]
        self._check_sorting_order(expected, result)

        result = self._check_artifact_get(
            '/withprops/v1.0/drafts?sort=name:asc')["artifacts"]
        self.assertEqual(5, len(result))

        expected = [art1, art2, art3, art4, art5]
        self._check_sorting_order(expected, result)

        result = self._check_artifact_get(
            '/withprops/v1.0/drafts?sort=version:asc,prop1')["artifacts"]
        self.assertEqual(5, len(result))

        expected = [art1, art3, art2, art4, art5]
        self._check_sorting_order(expected, result)

    def test_update_property(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        # update single integer property via PUT
        upd = self._check_artifact_put('/withprops/v1.0/%s/prop2' % art['id'],
                                       data={'data': 15})
        self.assertEqual(15, upd['prop2'])
        # create list property via PUT
        upd = self._check_artifact_put(
            '/withprops/v1.0/%s/tuple_prop' % art['id'],
            data={'data': [42, True]})
        self.assertEqual([42, True], upd['tuple_prop'])
        # change list property via PUT
        upd = self._check_artifact_put(
            '/withprops/v1.0/%s/tuple_prop/0' % art['id'], data={'data': 24})
        self.assertEqual([24, True], upd['tuple_prop'])
        # append to list property via POST
        upd = self._check_artifact_post(
            '/withprops/v1.0/%s/prop_list' % art['id'], data={'data': [11]},
            status=200)
        self.assertEqual([11], upd['prop_list'])
        # append to list property via POST
        upd = self._check_artifact_post(
            '/withprops/v1.0/%s/prop_list/-' % art['id'],
            status=200, data={'data': 10})
        self.assertEqual([11, 10], upd['prop_list'])

    def test_bad_update_property(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        # try to update nonexistent property
        upd = self._check_artifact_put(
            '/withprops/v1.0/%s/nosuchprop' % art['id'],
            data={'data': 'wont be set'}, status=400)
        self.assertIn('Artifact has no property nosuchprop', upd)
        # try to pass wrong property value
        upd = self._check_artifact_put(
            '/withprops/v1.0/%s/tuple_prop' % art['id'],
            data={'data': ['should be an int', False]}, status=400)
        self.assertIn("Property 'tuple_prop[0]' may not have value", upd)
        # try to pass bad body (not a valid json)
        upd = self._check_artifact_put(
            '/withprops/v1.0/%s/tuple_prop' % art['id'], data="not a json",
            status=400)
        self.assertIn("Invalid json body", upd)
        # try to pass json body invalid under schema
        upd = self._check_artifact_put(
            '/withprops/v1.0/%s/tuple_prop' % art['id'],
            data={"bad": "schema"}, status=400)
        self.assertIn("Invalid json body", upd)

    def test_update_different_depths_levels(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        upd = self._check_artifact_post(
            '/withprops/v1.0/%s/dict_prop' % art['id'],
            data={'data': {'foo': 'some value'}}, status=200)
        self.assertEqual({'foo': 'some value'}, upd['dict_prop'])
        upd = self._check_artifact_post(
            '/withprops/v1.0/%s/dict_prop/bar_list' % art['id'],
            data={'data': [5]}, status=200)
        self.assertEqual({'foo': 'some value', 'bar_list': [5]},
                         upd['dict_prop'])
        upd = self._check_artifact_post(
            '/withprops/v1.0/%s/dict_prop/bar_list/0' % art['id'],
            data={'data': 15}, status=200)
        self.assertEqual({'foo': 'some value', 'bar_list': [5, 15]},
                         upd['dict_prop'])
        # try to attempt dict_property by nonexistent path
        upd = self._check_artifact_post(
            '/withprops/v1.0/%s/dict_prop/bar_list/nosuchkey' % art['id'],
            data={'data': 15}, status=400)

    def test_artifact_inaccessible_by_different_user(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        self._set_user('user2')
        self._check_artifact_get('/withprops/%s' % art['id'], 404)

    def test_artifact_accessible_by_admin(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        self._set_user('admin')
        self._check_artifact_get('/withprops/%s' % art['id'], 200)

    def test_public_artifact_accessible_by_different_user(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        self._check_artifact_patch(
            '/withprops/v1.0/%s' % art['id'],
            data=[{'op': 'replace', 'value': 'public', 'path': '/visibility'}])
        self._set_user('user2')
        self._check_artifact_get('/withprops/%s' % art['id'], 200)

    def test_public_artifact_not_editable_by_different_user(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        self._check_artifact_patch(
            '/withprops/v1.0/%s' % art['id'],
            data=[{'op': 'replace', 'value': 'public', 'path': '/visibility'}])
        self._set_user('user2')
        self._check_artifact_patch(
            '/withprops/v1.0/%s' % art['id'],
            data=[{'op': 'replace', 'value': 'private',
                   'path': '/visibility'}], status=403)

    def test_public_artifact_editable_by_admin(self):
        data = {'name': 'an artifact',
                'version': '42'}
        art = self._create_artifact('withprops', data=data)
        self._check_artifact_patch(
            '/withprops/v1.0/%s' % art['id'],
            data=[{'op': 'replace', 'value': 'public', 'path': '/visibility'}])
        self._set_user('admin')
        self._check_artifact_patch(
            '/withprops/v1.0/%s' % art['id'],
            data=[{'op': 'replace', 'value': 'private',
                   'path': '/visibility'}], status=200)

    def test_list_artifact_types(self):
        actual = {
            u'artifact_types': [
                {u'displayed_name': u'NoProp',
                 u'type_name': u'NoProp',
                 u'versions':
                     [{u'id': u'v0.5',
                       u'link': u'http://127.0.0.1:%d/v3/artifacts/noprop/v0.5'
                                % self.api_port},
                      {u'id': u'v1.0',
                       u'link': u'http://127.0.0.1:%d/v3/artifacts/noprop/v1.0'
                                % self.api_port}]},
                {u'displayed_name': u'WithBlob',
                 u'type_name': u'WithBlob',
                 u'versions':
                     [{u'id': u'v1.0',
                       u'link':
                           u'http://127.0.0.1:%d/v3/artifacts/withblob/v1.0'
                           % self.api_port}]},
                {u'displayed_name': u'WithProps',
                 u'type_name': u'WithProps',
                 u'versions':
                     [{u'id': u'v1.0',
                       u'link':
                           u'http://127.0.0.1:%d/v3/artifacts/withprops/v1.0'
                           % self.api_port}]}]}

        response = self._check_artifact_get("", status=200)
        response[u'artifact_types'].sort(key=lambda x: x[u'type_name'])
        for artifact_type in response[u'artifact_types']:
            artifact_type[u'versions'].sort(key=lambda x: x[u'id'])

        self.assertEqual(actual, response)

    def test_filter_by_non_dict_props(self):
        data = {'name': 'art1',
                'version': '4.2',
                'prop2': 12
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'art2',
                'version': '4.2',
                'prop2': 10
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'art3',
                'version': '4.2',
                'prop2': 10
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'art4',
                'version': '4.3',
                'prop2': 33
                }
        self._create_artifact('withprops', data=data)

        result = self._check_artifact_get(
            '/withprops/v1.0/drafts?name=art2')['artifacts']
        self.assertEqual(1, len(result))

        result = self._check_artifact_get(
            '/withprops/v1.0/drafts?prop2=10')['artifacts']
        self.assertEqual(2, len(result))

    def test_filter_by_dict_props(self):
        data = {'name': 'art1',
                'version': '4.2',
                'dict_prop':
                    {'foo': 'Moscow',
                     'bar_list': [42, 44]}
                }
        self._create_artifact('withprops', data=data)
        data = {'name': 'art2',
                'version': '4.2',
                'dict_prop':
                    {'foo': 'Saratov',
                     'bar_list': [42, 42]}
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'art3',
                'version': '4.2',
                'dict_prop':
                    {'foo': 'Saratov',
                     'bar_list': [42, 44]}
                }
        self._create_artifact('withprops', data=data)

        url = '/withprops/v1.0/drafts?dict_prop.foo=Saratov'
        result = self._check_artifact_get(url=url)

        self.assertEqual(2, len(result))

        url = '/withprops/v1.0/drafts?dict_prop.bar_list=44'
        result = self._check_artifact_get(url=url)

        self.assertEqual(2, len(result))

    def test_transformation_versions(self):
        data = {'name': 'art1',
                'version': '1'}
        art1 = self._create_artifact('noprop', data=data)

        data = {'name': 'art2',
                'version': '1.0'}
        art2 = self._create_artifact('noprop', data=data)

        v1 = art1.get("version")
        v2 = art2.get("version")

        self.assertEqual('1.0.0', v1)
        self.assertEqual('1.0.0', v2)

    def test_filter_by_ge_version(self):
        data = {'name': 'art1',
                'version': '4.0.0'}
        art1 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.0.1'}
        art2 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-1'}
        art3 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-2'}
        art4 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0'}
        art5 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '5.0.0'}
        art6 = self._create_artifact('noprop', data=data)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:4.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:4.0.1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art2, art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:4.2.0-1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:4.2.0-2'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:4.2.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:5.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = [art6]
        self.assertEqual(actual, result)

    def test_filter_by_gt_version(self):
        data = {'name': 'art1',
                'version': '4.0.0'}
        self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.0.1'}
        art2 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-1'}
        art3 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-2'}
        art4 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0'}
        art5 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '5.0.0'}
        art6 = self._create_artifact('noprop', data=data)

        url = '/noprop/v1.0/drafts?name=art1&version=gt:4.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art2, art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=gt:4.0.1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=gt:4.2.0-1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=gt:4.2.0-2'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=gt:4.2.0'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = [art6]
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=gt:5.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = []
        self.assertEqual(actual, result)

    def test_filter_by_le_version(self):
        data = {'name': 'art1',
                'version': '4.0.0'}
        art1 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.0.1'}
        art2 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-1'}
        art3 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-2'}
        art4 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0'}
        art5 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '5.0.0'}
        art6 = self._create_artifact('noprop', data=data)

        url = '/noprop/v1.0/drafts?name=art1&version=le:4.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = [art1]
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=le:4.0.1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=le:4.2.0-1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=le:4.2.0-2'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=le:4.2.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4, art5]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=le:5.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

    def test_filter_by_lt_version(self):
        data = {'name': 'art1',
                'version': '4.0.0'}
        art1 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.0.1'}
        art2 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-1'}
        art3 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-2'}
        art4 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0'}
        art5 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '5.0.0'}
        self._create_artifact('noprop', data=data)

        url = '/noprop/v1.0/drafts?name=art1&version=lt:4.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = []
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=lt:4.0.1'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = [art1]
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=lt:4.2.0-1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=lt:4.2.0-2'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=lt:4.2.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=lt:5.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4, art5]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

    def test_filter_by_ne_version(self):
        data = {'name': 'art1',
                'version': '4.0.0'}
        art1 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.0.1'}
        art2 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-1'}
        art3 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-2'}
        art4 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0'}
        art5 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '5.0.0'}
        art6 = self._create_artifact('noprop', data=data)

        url = '/noprop/v1.0/drafts?name=art1&version=ne:4.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art2, art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ne:4.0.1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art3, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ne:4.2.0-1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art4, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ne:4.2.0-2'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art5, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ne:4.2.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4, art6]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ne:5.0.0'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2, art3, art4, art5]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

    def test_filter_by_pre_release_version(self):
        data = {'name': 'art1',
                'version': '4.2.0-1'}
        art1 = self._create_artifact('noprop', data=data)

        data = {'name': 'art1',
                'version': '4.2.0-2'}
        art2 = self._create_artifact('noprop', data=data)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:4.2.0-2'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = [art2]
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=le:4.2.0-2'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=ge:4.2.0-1'
        result = self._check_artifact_get(url=url)['artifacts']
        result.sort(key=lambda x: x['id'])

        actual = [art1, art2]
        actual.sort(key=lambda x: x['id'])
        self.assertEqual(actual, result)

        url = '/noprop/v1.0/drafts?name=art1&version=le:4.2.0-1'
        result = self._check_artifact_get(url=url)['artifacts']
        actual = [art1]
        self.assertEqual(actual, result)

    def test_filter_by_range_props(self):
        data = {'name': 'art1',
                'version': '4.2',
                'prop2': 10
                }
        self._create_artifact('withprops', data=data)
        data = {'name': 'art2',
                'version': '4.2',
                'prop2': 100
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'art3',
                'version': '4.2',
                'prop2': 1000
                }
        self._create_artifact('withprops', data=data)

        url = '/withprops/v1.0/drafts?prop2=gt:99&prop2=lt:101'
        result = self._check_artifact_get(url=url)['artifacts']

        self.assertEqual(1, len(result))

        url = '/withprops/v1.0/drafts?prop2=gt:99&prop2=lt:2000'
        result = self._check_artifact_get(url=url)['artifacts']

        self.assertEqual(2, len(result))

    def test_filter_by_tags(self):
        data = {'name': 'art1',
                'version': '4.2',
                'tags': ['hyhyhy', 'tytyty']
                }
        self._create_artifact('withprops', data=data)
        data = {'name': 'art2',
                'version': '4.2',
                'tags': ['hyhyhy', 'cicici']
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'art3',
                'version': '4.2',
                'tags': ['ededed', 'bobobo']
                }
        self._create_artifact('withprops', data=data)

        url = '/withprops/v1.0/drafts?tags=hyhyhy'
        result = self._check_artifact_get(url=url)['artifacts']

        self.assertEqual(2, len(result))

        url = '/withprops/v1.0/drafts?tags=cicici&tags=hyhyhy'
        result = self._check_artifact_get(url=url)['artifacts']

        self.assertEqual(1, len(result))

    def test_filter_by_latest_version(self):
        data = {'name': 'art1',
                'version': '1.2',
                'tags': ['hyhyhy', 'tytyty']
                }
        self._create_artifact('withprops', data=data)
        data = {'name': 'latest_artifact',
                'version': '3.2',
                'tags': ['hyhyhy', 'cicici']
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'latest_artifact',
                'version': '3.2',
                'tags': ['ededed', 'bobobo']
                }
        self._create_artifact('withprops', data=data)

        url = '/withprops/v1.0/drafts?version=latest&name=latest_artifact'
        result = self._check_artifact_get(url=url)

        self.assertEqual(2, len(result))

        url = '/withprops/v1.0/drafts?version=latest'
        self._check_artifact_get(url=url, status=400)

    def test_filter_by_version_only(self):
        data = {'name': 'art1',
                'version': '3.2'
                }
        self._create_artifact('withprops', data=data)
        data = {'name': 'art2',
                'version': '4.2'
                }
        self._create_artifact('withprops', data=data)

        data = {'name': 'art3',
                'version': '4.3'
                }
        self._create_artifact('withprops', data=data)

        url = '/withprops/v1.0/drafts?version=gt:4.0&version=lt:10.1'
        result = self._check_artifact_get(url=url)['artifacts']

        self.assertEqual(2, len(result))

        url = '/withprops/v1.0/drafts?version=gt:4.0&version=ne:4.3'
        result = self._check_artifact_get(url=url)['artifacts']

        self.assertEqual(1, len(result))
