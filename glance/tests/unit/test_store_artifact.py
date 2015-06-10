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
from datetime import datetime

from glance.artifacts.domain import proxy
from glance.artifacts import location
from glance.common.artifacts import definitions
import glance.context
from glance.tests.unit import utils as unit_test_utils
from glance.tests import utils


BASE_URI = 'http://storeurl.com/container'
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '228c6da5-29cd-4d67-9457-ed632e083fc0'


class ArtifactStub(definitions.ArtifactType):
    file = definitions.BinaryObject()
    file_list = definitions.BinaryObjectList()


class TestStoreArtifact(utils.BaseTestCase):
    def setUp(self):
        self.store_api = unit_test_utils.FakeStoreAPI()
        self.store_utils = unit_test_utils.FakeStoreUtils(self.store_api)
        ts = datetime.now()
        self.artifact_stub = ArtifactStub(id=UUID2, state='creating',
                                          created_at=ts, updated_at=ts,
                                          version='1.0', owner='me',
                                          name='foo')
        super(TestStoreArtifact, self).setUp()

    def test_set_blob_data(self):
        context = glance.context.RequestContext(user=USER1)
        helper = proxy.ArtifactHelper(location.ArtifactProxy,
                                      proxy_kwargs={
                                          'context': context,
                                          'store_api': self.store_api,
                                          'store_utils': self.store_utils
                                      })
        artifact = helper.proxy(self.artifact_stub)
        artifact.file = ('YYYY', 4)
        self.assertEqual(4, artifact.file.size)

    def test_set_bloblist_data(self):
        context = glance.context.RequestContext(user=USER1)
        helper = proxy.ArtifactHelper(location.ArtifactProxy,
                                      proxy_kwargs={
                                          'context': context,
                                          'store_api': self.store_api,
                                          'store_utils': self.store_utils
                                      })
        artifact = helper.proxy(self.artifact_stub)
        artifact.file_list.append(('YYYY', 4))
        self.assertEqual(4, artifact.file_list[0].size)
