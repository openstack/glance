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

import uuid

import six

import glance.artifacts as ga
from glance.common import exception as exc
from glance import context
import glance.tests.functional.db as db_tests
from glance.tests import utils as test_utils


UUID1, UUID2 = ('80cc6551-9db4-42aa-bb58-51c48757f285',
                'f89c675a-e01c-436c-a384-7d2e784fb2d9')
TYPE_NAME = u'TestArtifactType'
TYPE_VERSION = u'1.0.0'


class ArtifactsTestDriver(test_utils.BaseTestCase):
    def setUp(self):
        super(ArtifactsTestDriver, self).setUp()
        context_cls = context.RequestContext
        self.adm_context = context_cls(is_admin=True,
                                       auth_token='user:user:admin',
                                       tenant='admin-tenant')
        self.context = context_cls(is_admin=False,
                                   auth_token='user:user:user',
                                   tenant='test-tenant')
        self.db_api = db_tests.get_db(self.config)
        db_tests.reset_db(self.db_api)
        self.create_test_artifacts()

    def create_test_artifacts(self):
        dependency = {'2->1': [UUID1]}
        self.db_api.artifact_create(self.adm_context,
                                    get_fixture(id=UUID1,
                                                name="TestArtifact1",
                                                visibility="public"),
                                    TYPE_NAME,
                                    TYPE_VERSION)
        self.db_api.artifact_create(self.adm_context,
                                    get_fixture(id=UUID2,
                                                name="TestArtifact2",
                                                visibility="public",
                                                dependencies=dependency),
                                    TYPE_NAME,
                                    TYPE_VERSION)
        self.art1 = self.db_api.artifact_get(self.context, UUID1, TYPE_NAME,
                                             TYPE_VERSION)
        self.art2 = self.db_api.artifact_get(self.context, UUID2, TYPE_NAME,
                                             TYPE_VERSION)


class ArtifactTests(object):
    def test_artifact_create(self):
        artifact = get_fixture()
        created = self.db_api.artifact_create(self.context, artifact,
                                              TYPE_NAME, TYPE_VERSION)
        self.assertIsNotNone(created)
        self.assertEqual(artifact['name'], created['name'])
        self.assertEqual(artifact['type_name'], created['type_name'])
        self.assertEqual(artifact['type_version'], created['type_version'])

    def test_artifact_create_none_valued_props(self):
        artifact = get_fixture()
        artifact['properties']['lylyly'] = dict(value=None, type='int')
        artifact['properties']['hihihi'] = dict(value=5, type='int')
        created = self.db_api.artifact_create(self.context, artifact,
                                              TYPE_NAME, TYPE_VERSION)
        self.assertIsNotNone(created)
        self.assertIn('hihihi', created['properties'])
        self.assertNotIn('lylyly', created['properties'])

    def test_artifact_update(self):
        fixture = {'name': 'UpdatedName'}
        updated = self.db_api.artifact_update(self.context, fixture, UUID1,
                                              TYPE_NAME, TYPE_VERSION)
        self.assertIsNotNone(updated)
        self.assertEqual('UpdatedName', updated['name'])
        self.assertNotEqual(updated['created_at'], updated['updated_at'])

    def test_artifact_create_same_version_different_users(self):
        tenant1 = str(uuid.uuid4())
        tenant2 = str(uuid.uuid4())
        ctx1 = context.RequestContext(is_admin=False, tenant=tenant1)
        ctx2 = context.RequestContext(is_admin=False, tenant=tenant2)
        artifact1 = get_fixture(owner=tenant1)
        artifact2 = get_fixture(owner=tenant2)
        self.db_api.artifact_create(ctx1, artifact1,
                                    TYPE_NAME, TYPE_VERSION)

        self.assertIsNotNone(
            self.db_api.artifact_create(ctx2, artifact2,
                                        TYPE_NAME, TYPE_VERSION))

    def test_artifact_create_same_version_deleted(self):
        artifact1 = get_fixture()
        artifact2 = get_fixture(state='deleted')
        artifact3 = get_fixture(state='deleted')
        self.db_api.artifact_create(self.context, artifact1,
                                    TYPE_NAME, TYPE_VERSION)

        self.assertIsNotNone(
            self.db_api.artifact_create(self.context, artifact2,
                                        TYPE_NAME, TYPE_VERSION))
        self.assertIsNotNone(
            self.db_api.artifact_create(self.context, artifact3,
                                        TYPE_NAME, TYPE_VERSION))

    def test_artifact_get(self):
        res = self.db_api.artifact_get(self.context, UUID1,
                                       TYPE_NAME, TYPE_VERSION)
        self.assertEqual('TestArtifact1', res['name'])
        self.assertEqual('TestArtifactType', res['type_name'])
        self.assertEqual('1.0.0', res['type_version'])
        self.assertEqual('10.0.3-alpha+some-date', res['version'])
        self.assertEqual('creating', res['state'])
        self.assertEqual('test-tenant', res['owner'])

    def test_artifact_get_owned(self):
        tenant1 = str(uuid.uuid4())
        tenant2 = str(uuid.uuid4())
        ctx1 = context.RequestContext(is_admin=False, tenant=tenant1)
        ctx2 = context.RequestContext(is_admin=False, tenant=tenant2)

        artifact = get_fixture(owner=tenant1)
        created = self.db_api.artifact_create(ctx1, artifact,
                                              TYPE_NAME, TYPE_VERSION)
        self.assertIsNotNone(self.db_api.artifact_get(ctx1, created['id'],
                                                      TYPE_NAME, TYPE_VERSION))
        self.assertRaises(exc.ArtifactForbidden, self.db_api.artifact_get,
                          ctx2, created['id'], TYPE_NAME, TYPE_VERSION)

    def test_artifact_get_public(self):
        tenant1 = str(uuid.uuid4())
        tenant2 = str(uuid.uuid4())
        ctx1 = context.RequestContext(is_admin=False, tenant=tenant1)
        ctx2 = context.RequestContext(is_admin=False, tenant=tenant2)

        artifact = get_fixture(owner=tenant1, visibility='public')
        created = self.db_api.artifact_create(ctx1, artifact,
                                              TYPE_NAME, TYPE_VERSION)
        self.assertIsNotNone(self.db_api.artifact_get(ctx1, created['id'],
                                                      TYPE_NAME, TYPE_VERSION))
        self.assertIsNotNone(self.db_api.artifact_get(ctx2, created['id'],
                                                      TYPE_NAME, TYPE_VERSION))

    def test_artifact_update_state(self):
        res = self.db_api.artifact_update(self.context, {'state': 'active'},
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        self.assertEqual('active', res['state'])

        self.assertRaises(exc.InvalidArtifactStateTransition,
                          self.db_api.artifact_update, self.context,
                          {'state': 'creating'}, UUID1,
                          TYPE_NAME, TYPE_VERSION)

        res = self.db_api.artifact_update(self.context,
                                          {'state': 'deactivated'}, UUID1,
                                          TYPE_NAME, TYPE_VERSION)
        self.assertEqual('deactivated', res['state'])
        res = self.db_api.artifact_update(self.context, {'state': 'active'},
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        self.assertEqual('active', res['state'])
        res = self.db_api.artifact_update(self.context, {'state': 'deleted'},
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        self.assertEqual('deleted', res['state'])

        self.assertRaises(exc.InvalidArtifactStateTransition,
                          self.db_api.artifact_update, self.context,
                          {'state': 'active'}, UUID1,
                          TYPE_NAME, TYPE_VERSION)
        self.assertRaises(exc.InvalidArtifactStateTransition,
                          self.db_api.artifact_update, self.context,
                          {'state': 'deactivated'}, UUID1,
                          TYPE_NAME, TYPE_VERSION)
        self.assertRaises(exc.InvalidArtifactStateTransition,
                          self.db_api.artifact_update, self.context,
                          {'state': 'creating'}, UUID1,
                          TYPE_NAME, TYPE_VERSION)

    def test_artifact_update_tags(self):
        res = self.db_api.artifact_update(self.context,
                                          {'tags': ['gagaga', 'lalala']},
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        self.assertEqual(set(['gagaga', 'lalala']), set(res['tags']))

    def test_artifact_update_properties(self):
        new_properties = {'properties': {
            'propname1': {
                'type': 'string',
                'value': 'qeqeqe'},
            'propname2': {
                'type': 'int',
                'value': 6},
            'propname3': {
                'type': 'int',
                'value': '5'},
            'proparray': {
                'type': 'string',
                'value': 'notarray'
            }}
        }
        res = self.db_api.artifact_update(self.context,
                                          new_properties,
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        bd_properties = res['properties']
        self.assertEqual(4, len(bd_properties))

        for prop in bd_properties:
            self.assertIn(prop, new_properties['properties'])

    def test_artifact_update_blobs(self):
        new_blobs = {'blobs': {
            'blob1': [{
                'size': 2600000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL11',
                     'status': 'active'},
                    {'value': 'URL12',
                     'status': 'active'}]
            }, {
                'size': 200000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'newURL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'passive'}]
            }
            ],
            'blob2': [{
                'size': 120000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'active'}]
            }, {
                'size': 300000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'bl1URL2',
                     'status': 'passive'}]
            }
            ]
        }

        }
        res = self.db_api.artifact_update(self.context,
                                          new_blobs,
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        bd_blobs = res['blobs']
        self.assertEqual(2, len(bd_blobs))
        for blob in bd_blobs:
            self.assertIn(blob, new_blobs['blobs'])

    def test_artifact_create_with_dependency(self):
        dependencies = {"new->2": [UUID2]}
        artifact = get_fixture(dependencies=dependencies)
        res = self.db_api.artifact_create(self.context, artifact,
                                          TYPE_NAME, TYPE_VERSION)
        self.assertIsNotNone(res)

        created = self.db_api.artifact_get(
            self.context, res['id'], TYPE_NAME, TYPE_VERSION,
            show_level=ga.Showlevel.DIRECT)
        bd_dependencies = created['dependencies']
        self.assertEqual(1, len(bd_dependencies))
        # now try to update artifact with the same dependency
        new_dependencies = {"dependencies": {"new->2": [UUID2],
                                             "new->3": [UUID2]}}
        res = self.db_api.artifact_update(self.context,
                                          new_dependencies,
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        retrieved = self.db_api.artifact_get(
            self.context, res['id'],
            TYPE_NAME, TYPE_VERSION, show_level=ga.Showlevel.DIRECT)
        self.assertEqual(2, len(retrieved["dependencies"]))

    def test_artifact_create_transitive_dependencies(self):
        dependencies = {"new->2": [UUID2]}
        artifact = get_fixture(dependencies=dependencies, id='new')
        res = self.db_api.artifact_create(self.context, artifact,
                                          TYPE_NAME, TYPE_VERSION)
        self.assertIsNotNone(res)

        created = self.db_api.artifact_get(
            self.context, res['id'], TYPE_NAME, TYPE_VERSION,
            show_level=ga.Showlevel.DIRECT)
        bd_dependencies = created['dependencies']
        self.assertEqual(1, len(bd_dependencies))

        res = self.db_api.artifact_publish(
            self.context,
            res['id'], TYPE_NAME, TYPE_VERSION
        )

        res = self.db_api.artifact_get(
            self.context, res['id'], TYPE_NAME, TYPE_VERSION,
            show_level=ga.Showlevel.TRANSITIVE)
        self.assertIsNotNone(res.pop('created_at'))
        self.assertIsNotNone(res.pop('updated_at'))

        # NOTE(mfedosin): tags is a set, so we have to check it separately
        tags = res.pop('tags', None)
        self.assertIsNotNone(tags)
        self.assertEqual(set(['gugugu', 'lalala']), set(tags))

        tags = res['dependencies']['new->2'][0].pop('tags', None)
        self.assertIsNotNone(tags)
        self.assertEqual(set(['gugugu', 'lalala']), set(tags))

        tags = (res['dependencies']['new->2'][0]['dependencies']['2->1'][0].
                pop('tags', None))
        self.assertIsNotNone(tags)
        self.assertEqual(set(['gugugu', 'lalala']), set(tags))

        expected = {
            'id': 'new',
            'name': u'SomeArtifact',
            'description': None,
            'type_name': TYPE_NAME,
            'type_version': TYPE_VERSION,
            'version': u'10.0.3-alpha+some-date',
            'visibility': u'private',
            'state': u'active',
            'owner': u'test-tenant',
            'published_at': None,
            'deleted_at': None,
            'properties': {
                'propname1': {
                    'type': 'string',
                    'value': 'tututu'},
                'propname2': {
                    'type': 'int',
                    'value': 5},
                'propname3': {
                    'type': 'string',
                    'value': 'vavava'},
                'proparray': {
                    'type': 'array',
                    'value': [
                        {'type': 'int',
                         'value': 6},
                        {'type': 'string',
                         'value': 'rerere'}
                    ]
                }
            },
            'blobs': {
                'blob1': [{
                    'size': 1600000,
                    'checksum': 'abc',
                    'item_key': 'some',
                    'locations': [
                        {'value': 'URL11',
                         'status': 'active'},
                        {'value': 'URL12',
                         'status': 'active'}]
                }, {
                    'size': 100000,
                    'checksum': 'abc',
                    'item_key': 'some',
                    'locations': [
                        {'value': 'URL21',
                         'status': 'active'},
                        {'value': 'URL22',
                         'status': 'active'}]
                }]
            },
            'dependencies': {
                'new->2': [
                    {
                        'id': UUID2,
                        'created_at': self.art2['created_at'],
                        'updated_at': self.art2['updated_at'],
                        'published_at': None,
                        'deleted_at': None,
                        'name': u'TestArtifact2',
                        'description': None,
                        'type_name': TYPE_NAME,
                        'type_version': TYPE_VERSION,
                        'version': u'10.0.3-alpha+some-date',
                        'visibility': 'public',
                        'state': u'creating',
                        'owner': u'test-tenant',
                        'properties': {
                            'propname1': {
                                'type': 'string',
                                'value': 'tututu'},
                            'propname2': {
                                'type': 'int',
                                'value': 5},
                            'propname3': {
                                'type': 'string',
                                'value': 'vavava'},
                            'proparray': {
                                'type': 'array',
                                'value': [
                                    {'type': 'int',
                                     'value': 6},
                                    {'type': 'string',
                                     'value': 'rerere'}
                                ]
                            }
                        },
                        'blobs': {
                            'blob1': [{
                                'size': 1600000,
                                'checksum': 'abc',
                                'item_key': 'some',
                                'locations': [
                                    {'value': 'URL11',
                                     'status': 'active'},
                                    {'value': 'URL12',
                                     'status': 'active'}]
                            }, {
                                'size': 100000,
                                'checksum': 'abc',
                                'item_key': 'some',
                                'locations': [
                                    {'value': 'URL21',
                                     'status': 'active'},
                                    {'value': 'URL22',
                                     'status': 'active'}]
                            }]
                        },
                        'dependencies': {
                            '2->1': [
                                {
                                    'id': UUID1,
                                    'created_at': self.art1['created_at'],
                                    'updated_at': self.art1['updated_at'],
                                    'published_at': None,
                                    'deleted_at': None,
                                    'dependencies': {},
                                    'name': u'TestArtifact1',
                                    'description': None,
                                    'type_name': TYPE_NAME,
                                    'type_version': TYPE_VERSION,
                                    'version': u'10.0.3-alpha+some-date',
                                    'visibility': 'public',
                                    'state': u'creating',
                                    'owner': u'test-tenant',
                                    'properties': {
                                        'propname1': {
                                            'type': 'string',
                                            'value': 'tututu'},
                                        'propname2': {
                                            'type': 'int',
                                            'value': 5},
                                        'propname3': {
                                            'type': 'string',
                                            'value': 'vavava'},
                                        'proparray': {
                                            'type': 'array',
                                            'value': [
                                                {'type': 'int',
                                                 'value': 6},
                                                {'type': 'string',
                                                 'value': 'rerere'}
                                            ]
                                        }
                                    },
                                    'blobs': {
                                        'blob1': [{
                                            'size': 1600000,
                                            'checksum': 'abc',
                                            'item_key': 'some',
                                            'locations': [
                                                {'value': 'URL11',
                                                 'status': 'active'},
                                                {'value': 'URL12',
                                                 'status': 'active'}]
                                        }, {
                                            'size': 100000,
                                            'checksum': 'abc',
                                            'item_key': 'some',
                                            'locations': [
                                                {'value': 'URL21',
                                                 'status': 'active'},
                                                {'value': 'URL22',
                                                 'status': 'active'}]
                                        }]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
        self.assertIsNotNone(res['published_at'])
        published_at = res['published_at']
        expected['published_at'] = published_at
        for key, value in six.iteritems(expected):
            self.assertEqual(expected[key], res[key])

    def test_artifact_get_all(self):
        artifact = get_fixture(name='new_artifact')
        self.db_api.artifact_create(self.context, artifact,
                                    TYPE_NAME, TYPE_VERSION)
        artifacts = self.db_api.artifact_get_all(self.context)
        self.assertEqual(3, len(artifacts))

    def test_artifact_sort_order(self):
        arts = [get_fixture(version='1.2.3-alpha.4.df.00f'),
                get_fixture(version='1.2.2'),
                get_fixture(version='1.2.3+some-metadata'),
                get_fixture(version='1.2.4'),
                get_fixture(version='1.2.3-release.2'),
                get_fixture(version='1.2.3-release.1+metadata'),
                get_fixture(version='1.2.3-final'),
                get_fixture(version='1.2.3-alpha.14.df.00f')]
        for art in arts:
            self.db_api.artifact_create(self.context, art, TYPE_NAME,
                                        TYPE_VERSION)
        artifacts = self.db_api.artifact_get_all(self.context,
                                                 sort_keys=[('version',
                                                             None)],
                                                 sort_dirs=['asc'])

        expected_versions = [
            '1.2.2',
            '1.2.3-alpha.4.df.00f',
            '1.2.3-alpha.14.df.00f',
            '1.2.3-final',
            '1.2.3-release.1+metadata',
            '1.2.3-release.2',
            '1.2.3+some-metadata',
            '1.2.4']
        for i in xrange(len(expected_versions)):
            self.assertEqual(expected_versions[i], artifacts[i]['version'])

    def test_artifact_get_all_show_level(self):
        artifacts = self.db_api.artifact_get_all(self.context)
        self.assertEqual(2, len(artifacts))

        self.assertRaises(KeyError, lambda: artifacts[0]['properties'])

        artifacts = self.db_api.artifact_get_all(
            self.context, show_level=ga.Showlevel.BASIC)
        self.assertEqual(2, len(artifacts))
        self.assertEqual(4, len(artifacts[0]['properties']))

        self.assertRaises(exc.ArtifactUnsupportedShowLevel,
                          self.db_api.artifact_get_all, self.context,
                          show_level=ga.Showlevel.DIRECT)

    def test_artifact_get_all_tags(self):
        artifact = get_fixture(name='new_artifact',
                               tags=['qwerty', 'uiop'])
        self.db_api.artifact_create(self.context, artifact,
                                    TYPE_NAME, TYPE_VERSION)
        artifacts = self.db_api.artifact_get_all(self.context)
        self.assertEqual(3, len(artifacts))

        filters = {'tags': [{
            'value': 'notag',
        }]}
        artifacts = self.db_api.artifact_get_all(self.context, filters=filters)
        self.assertEqual(0, len(artifacts))

        filters = {'tags': [{
            'value': 'lalala',
        }]}
        artifacts = self.db_api.artifact_get_all(self.context, filters=filters)
        self.assertEqual(2, len(artifacts))
        for artifact in artifacts:
            self.assertIn(artifact['name'], ['TestArtifact1', 'TestArtifact2'])

    def test_artifact_get_all_properties(self):
        artifact = get_fixture(
            name='new_artifact',
            properties={
                'newprop2': {
                    'type': 'string',
                    'value': 'tututu'},
                'propname2': {
                    'type': 'int',
                    'value': 3},
                'propname3': {
                    'type': 'string',
                    'value': 'vavava'},
                'proptext': {
                    'type': 'text',
                    'value': 'bebebe' * 100},
                'proparray': {
                    'type': 'array',
                    'value': [
                        {'type': 'int',
                         'value': 17},
                        {'type': 'string',
                         'value': 'rerere'}
                    ]
                }})
        self.db_api.artifact_create(self.context, artifact,
                                    TYPE_NAME, TYPE_VERSION)

        filters = {'propname2': [{
            'value': 4,
            'operator': 'GT',
            'type': 'int'}]}
        artifacts = self.db_api.artifact_get_all(self.context, filters=filters)
        self.assertEqual(2, len(artifacts))
        for artifact in artifacts:
            self.assertIn(artifact['name'], ['TestArtifact1', 'TestArtifact2'])

        # position hasn't been set
        filters = {'proparray': [{
            'value': 6,
            'operator': 'LE',
            'type': 'int'}]}
        artifacts = self.db_api.artifact_get_all(self.context, filters=filters)
        self.assertEqual(0, len(artifacts))
        for artifact in artifacts:
            self.assertIn(artifact['name'], ['TestArtifact1', 'TestArtifact2'])

        # position has been set
        filters = {'proparray': [{
            'value': 6,
            'position': 0,
            'operator': 'LE',
            'type': 'int'}]}
        artifacts = self.db_api.artifact_get_all(self.context, filters=filters)
        self.assertEqual(2, len(artifacts))
        for artifact in artifacts:
            self.assertIn(artifact['name'], ['TestArtifact1', 'TestArtifact2'])

        filters = {'proparray': [{
            'value': 6,
            'operator': 'IN',
            'type': 'int'}]}
        artifacts = self.db_api.artifact_get_all(self.context, filters=filters)
        self.assertEqual(2, len(artifacts))
        for artifact in artifacts:
            self.assertIn(artifact['name'], ['TestArtifact1', 'TestArtifact2'])

        filters = {'name': [{'value': 'new_artifact'}]}
        artifacts = self.db_api.artifact_get_all(self.context,
                                                 filters=filters,
                                                 show_level=ga.Showlevel.BASIC)
        self.assertEqual(1, len(artifacts))
        artifact = artifacts[0]
        self.assertEqual('new_artifact', artifact['name'])
        for prop in artifact['properties'].keys():
            self.assertNotEqual('proptext', prop)

        filters = {'propname2': [{
            'value': 4,
            'operator': 'FOO',
            'type': 'int'}]}
        self.assertRaises(
            exc.ArtifactUnsupportedPropertyOperator,
            self.db_api.artifact_get_all, self.context, filters=filters)

    def test_artifact_delete(self):
        res = self.db_api.artifact_delete(self.context, UUID1,
                                          TYPE_NAME, TYPE_VERSION)
        self.assertEqual('TestArtifact1', res['name'])
        self.assertEqual('deleted', res['state'])
        self.assertIsNotNone(res['deleted_at'])

        artifacts = self.db_api.artifact_get_all(self.context)
        self.assertEqual(1, len(artifacts))

    def test_artifact_delete_property(self):

        new_properties = {'properties': {
            'proparray': {'value': [],
                          'type': 'array'}
        }
        }
        res = self.db_api.artifact_update(self.context,
                                          new_properties,
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        bd_properties = res['properties']
        self.assertEqual(3, len(bd_properties))

        expected = {
            'propname1': {
                'type': 'string',
                'value': 'tututu'},
            'propname2': {
                'type': 'int',
                'value': 5},
            'propname3': {
                'type': 'string',
                'value': 'vavava'}
        }

        for prop in bd_properties:
            self.assertIn(prop, expected)

    def test_artifact_delete_blob(self):

        new_blobs = {'blobs': {
            'blob2': [{
                'size': 2600000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL11',
                     'status': 'active'},
                    {'value': 'URL12',
                     'status': 'active'}]
            }, {
                'size': 200000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'newURL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'passive'}]
            }
            ],
            'blob3': [{
                'size': 120000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'active'}]
            }, {
                'size': 300000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'bl1URL2',
                     'status': 'passive'}]
            }
            ]
        }

        }

        expected = {'blobs': {
            'blob1': [{
                'size': 1600000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL11',
                     'status': 'active'},
                    {'value': 'URL12',
                     'status': 'active'}]
            }, {
                'size': 100000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'active'}]
            }
            ],
            'blob2': [{
                'size': 2600000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL11',
                     'status': 'active'},
                    {'value': 'URL12',
                     'status': 'active'}]
            }, {
                'size': 200000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'newURL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'passive'}]
            }
            ],
            'blob3': [{
                'size': 120000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'active'}]
            }, {
                'size': 300000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'bl1URL2',
                     'status': 'passive'}]
            }
            ]
        }

        }

        res = self.db_api.artifact_update(self.context,
                                          new_blobs,
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        bd_blobs = res['blobs']
        self.assertEqual(3, len(bd_blobs))
        for blob in bd_blobs:
            self.assertIn(blob, expected['blobs'])

        del_blobs = {'blobs': {
            'blob1': []}
        }

        res = self.db_api.artifact_update(self.context,
                                          del_blobs,
                                          UUID1, TYPE_NAME, TYPE_VERSION)
        bd_blobs = res['blobs']
        self.assertEqual(2, len(bd_blobs))

        for blob in bd_blobs:
            self.assertIn(blob, new_blobs['blobs'])


def get_fixture(**kwargs):
    artifact = {
        'name': u'SomeArtifact',
        'type_name': TYPE_NAME,
        'type_version': TYPE_VERSION,
        'version': u'10.0.3-alpha+some-date',
        'visibility': u'private',
        'state': u'creating',
        'owner': u'test-tenant',
        'tags': ['lalala', 'gugugu'],
        'properties': {
            'propname1': {
                'type': 'string',
                'value': 'tututu'},
            'propname2': {
                'type': 'int',
                'value': 5},
            'propname3': {
                'type': 'string',
                'value': 'vavava'},
            'proparray': {
                'type': 'array',
                'value': [
                    {'type': 'int',
                     'value': 6},
                    {'type': 'string',
                     'value': 'rerere'}
                ]
            }
        },
        'blobs': {
            'blob1': [{
                'size': 1600000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL11',
                     'status': 'active'},
                    {'value': 'URL12',
                     'status': 'active'}]
            }, {
                'size': 100000,
                'checksum': 'abc',
                'item_key': 'some',
                'locations': [
                    {'value': 'URL21',
                     'status': 'active'},
                    {'value': 'URL22',
                     'status': 'active'}]
            }
            ]
        }
    }

    artifact.update(kwargs)
    return artifact
