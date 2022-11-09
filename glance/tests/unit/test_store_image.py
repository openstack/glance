# Copyright 2012 OpenStack Foundation
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
from cryptography import exceptions as crypto_exception
from cursive import exception as cursive_exception
from cursive import signature_utils
import glance_store
from unittest import mock

from glance.common import exception
import glance.location
from glance.tests.unit import base as unit_test_base
from glance.tests.unit import utils as unit_test_utils
from glance.tests import utils


BASE_URI = 'http://storeurl.com/container'
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '228c6da5-29cd-4d67-9457-ed632e083fc0'


class ImageRepoStub(object):
    def add(self, image):
        return image

    def save(self, image, from_state=None):
        return image


class ImageStub(object):
    def __init__(self, image_id, status=None, locations=None,
                 visibility=None, extra_properties=None):
        self.image_id = image_id
        self.status = status
        self.locations = locations or []
        self.visibility = visibility
        self.size = None
        self.extra_properties = extra_properties or {}
        self.os_hash_algo = None
        self.os_hash_value = None
        self.checksum = None
        self.disk_format = 'raw'
        self.container_format = 'bare'
        self.virtual_size = 0

    def delete(self):
        self.status = 'deleted'

    def get_member_repo(self):
        return FakeMemberRepo(self, [TENANT1, TENANT2])


class ImageFactoryStub(object):
    def new_image(self, image_id=None, name=None, visibility='private',
                  min_disk=0, min_ram=0, protected=False, owner=None,
                  disk_format=None, container_format=None,
                  extra_properties=None, tags=None, **other_args):
        return ImageStub(image_id, visibility=visibility,
                         extra_properties=extra_properties, **other_args)


class FakeMemberRepo(object):
    def __init__(self, image, tenants=None):
        self.image = image
        self.factory = glance.domain.ImageMemberFactory()
        self.tenants = tenants or []

    def list(self, *args, **kwargs):
        return [self.factory.new_image_member(self.image, tenant)
                for tenant in self.tenants]

    def add(self, member):
        self.tenants.append(member.member_id)

    def remove(self, member):
        self.tenants.remove(member.member_id)


class TestStoreMultiBackends(utils.BaseTestCase):
    def setUp(self):
        self.store_api = unit_test_utils.FakeStoreAPI()
        self.store_utils = unit_test_utils.FakeStoreUtils(self.store_api)
        self.enabled_backends = {
            "ceph1": "rbd",
            "ceph2": "rbd"
        }
        super(TestStoreMultiBackends, self).setUp()
        self.config(enabled_backends=self.enabled_backends)

    @mock.patch("glance.location.signature_utils.get_verifier")
    def test_set_data_calls_upload_to_store(self, msig):
        context = glance.context.RequestContext(user=USER1)
        extra_properties = {
            'img_signature_certificate_uuid': 'UUID',
            'img_signature_hash_method': 'METHOD',
            'img_signature_key_type': 'TYPE',
            'img_signature': 'VALID'
        }
        image_stub = ImageStub(UUID2, status='queued', locations=[],
                               extra_properties=extra_properties)
        image_stub.disk_format = 'iso'
        image = glance.location.ImageProxy(image_stub, context,
                                           self.store_api, self.store_utils)
        with mock.patch.object(image, "_upload_to_store") as mloc:
            image.set_data('YYYY', 4, backend='ceph1')
            msig.assert_called_once_with(context=context,
                                         img_signature_certificate_uuid='UUID',
                                         img_signature_hash_method='METHOD',
                                         img_signature='VALID',
                                         img_signature_key_type='TYPE')
            mloc.assert_called_once_with('YYYY', msig.return_value, 'ceph1', 4)

        self.assertEqual('active', image.status)

    def test_image_set_data(self):
        store_api = mock.MagicMock()
        store_api.add_with_multihash.return_value = (
            "rbd://ceph1", 4, "Z", "MH", {"backend": "ceph1"})
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, self.store_utils)
        image.set_data('YYYY', 4, backend='ceph1')
        self.assertEqual(4, image.size)

        # NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual("rbd://ceph1", image.locations[0]['url'])
        self.assertEqual({"backend": "ceph1"}, image.locations[0]['metadata'])
        self.assertEqual('Z', image.checksum)
        self.assertEqual('active', image.status)

    @mock.patch('glance.location.LOG')
    def test_image_set_data_valid_signature(self, mock_log):
        store_api = mock.MagicMock()
        store_api.add_with_multihash.return_value = (
            "rbd://ceph1", 4, "Z", "MH", {"backend": "ceph1"})
        context = glance.context.RequestContext(user=USER1)
        extra_properties = {
            'img_signature_certificate_uuid': 'UUID',
            'img_signature_hash_method': 'METHOD',
            'img_signature_key_type': 'TYPE',
            'img_signature': 'VALID'
        }
        image_stub = ImageStub(UUID2, status='queued',
                               extra_properties=extra_properties)
        self.mock_object(signature_utils, 'get_verifier',
                         unit_test_utils.fake_get_verifier)
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, self.store_utils)
        image.set_data('YYYY', 4, backend='ceph1')
        self.assertEqual('active', image.status)
        call = mock.call('Successfully verified signature for image %s',
                         UUID2)
        mock_log.info.assert_has_calls([call])

    @mock.patch("glance.location.signature_utils.get_verifier")
    def test_image_set_data_invalid_signature(self, msig):
        msig.return_value.verify.side_effect = \
            crypto_exception.InvalidSignature
        store_api = mock.MagicMock()
        store_api.add_with_multihash.return_value = (
            "rbd://ceph1", 4, "Z", "MH", {"backend": "ceph1"})
        context = glance.context.RequestContext(user=USER1)
        extra_properties = {
            'img_signature_certificate_uuid': 'UUID',
            'img_signature_hash_method': 'METHOD',
            'img_signature_key_type': 'TYPE',
            'img_signature': 'INVALID'
        }
        image_stub = ImageStub(UUID2, status='queued',
                               extra_properties=extra_properties)
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, self.store_utils)
        self.assertRaises(cursive_exception.SignatureVerificationError,
                          image.set_data, 'YYYY', 4, backend='ceph1')


class TestStoreImage(utils.BaseTestCase):
    def setUp(self):
        locations = [{'url': '%s/%s' % (BASE_URI, UUID1),
                      'metadata': {}, 'status': 'active'}]
        self.image_stub = ImageStub(UUID1, 'active', locations)
        self.store_api = unit_test_utils.FakeStoreAPI()
        self.store_utils = unit_test_utils.FakeStoreUtils(self.store_api)
        super(TestStoreImage, self).setUp()

    def test_image_delete(self):
        image = glance.location.ImageProxy(self.image_stub, {},
                                           self.store_api, self.store_utils)
        location = image.locations[0]
        self.assertEqual('active', image.status)
        self.store_api.get_from_backend(location['url'], context={})
        image.delete()
        self.assertEqual('deleted', image.status)
        self.assertRaises(glance_store.NotFound,
                          self.store_api.get_from_backend, location['url'], {})

    def test_image_get_data(self):
        image = glance.location.ImageProxy(self.image_stub, {},
                                           self.store_api, self.store_utils)
        self.assertEqual('XXX', image.get_data())

    def test_image_get_data_from_second_location(self):
        def fake_get_from_backend(self, location, offset=0,
                                  chunk_size=None, context=None):
            if UUID1 in location:
                raise Exception('not allow download from %s' % location)
            else:
                return self.data[location]

        image1 = glance.location.ImageProxy(self.image_stub, {},
                                            self.store_api, self.store_utils)
        self.assertEqual('XXX', image1.get_data())
        # Multiple location support
        context = glance.context.RequestContext(user=USER1)
        (image2, image_stub2) = self._add_image(context, UUID2, 'ZZZ', 3)
        location_data = image2.locations[0]

        with mock.patch("glance.location.store") as mock_store:
            mock_store.get_size_from_uri_and_backend.return_value = 3
            image1.locations.append(location_data)

        self.assertEqual(2, len(image1.locations))
        self.assertEqual(UUID2, location_data['url'])

        self.mock_object(unit_test_utils.FakeStoreAPI, 'get_from_backend',
                         fake_get_from_backend)
        # This time, image1.get_data() returns the data wrapped in a
        # LimitingReader|CooperativeReader|InfoWrapper pipeline, so
        # peeking under the hood of those objects to get at the
        # underlying string.
        self.assertEqual('ZZZ', image1.get_data().data.fd._source)

        image1.locations.pop(0)
        self.assertEqual(1, len(image1.locations))
        image2.delete()

    def test_image_set_data(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        # We are going to pass an iterable data source, so use the
        # FakeStoreAPIReader that actually reads from that data
        store_api = unit_test_utils.FakeStoreAPIReader()
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, self.store_utils)
        image.set_data(iter(['YYYY']), 4)
        self.assertEqual(4, image.size)
        # NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual(UUID2, image.locations[0]['url'])
        self.assertEqual('Z', image.checksum)
        self.assertEqual('active', image.status)
        self.assertEqual(4, image.virtual_size)

    def test_image_set_data_inspector_no_match(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image_stub.disk_format = 'qcow2'
        # We are going to pass an iterable data source, so use the
        # FakeStoreAPIReader that actually reads from that data
        store_api = unit_test_utils.FakeStoreAPIReader()
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, self.store_utils)
        image.set_data(iter(['YYYY']), 4)
        self.assertEqual(4, image.size)
        # NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual(UUID2, image.locations[0]['url'])
        self.assertEqual('Z', image.checksum)
        self.assertEqual('active', image.status)
        self.assertEqual(0, image.virtual_size)

    @mock.patch('glance.common.format_inspector.QcowInspector.virtual_size',
                new_callable=mock.PropertyMock)
    @mock.patch('glance.common.format_inspector.QcowInspector.format_match',
                new_callable=mock.PropertyMock)
    def test_image_set_data_inspector_virtual_size_failure(self, mock_fm,
                                                           mock_vs):
        # Force our format to match
        mock_fm.return_value = True

        # Make virtual_size fail in some unexpected way
        mock_vs.side_effect = ValueError('some error')

        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image_stub.disk_format = 'qcow2'
        # We are going to pass an iterable data source, so use the
        # FakeStoreAPIReader that actually reads from that data
        store_api = unit_test_utils.FakeStoreAPIReader()
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, self.store_utils)

        # Make sure set_data proceeds even though the format clearly
        # does not match
        image.set_data(iter(['YYYY']), 4)
        self.assertEqual(4, image.size)
        # NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual(UUID2, image.locations[0]['url'])
        self.assertEqual('Z', image.checksum)
        self.assertEqual('active', image.status)
        self.assertEqual(0, image.virtual_size)

    @mock.patch('glance.common.format_inspector.get_inspector')
    def test_image_set_data_inspector_not_needed(self, mock_gi):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image_stub.virtual_size = 123
        image_stub.disk_format = 'qcow2'
        # We are going to pass an iterable data source, so use the
        # FakeStoreAPIReader that actually reads from that data
        store_api = unit_test_utils.FakeStoreAPIReader()
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, self.store_utils)
        image.set_data(iter(['YYYY']), 4)
        self.assertEqual(4, image.size)
        # NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual(UUID2, image.locations[0]['url'])
        self.assertEqual('Z', image.checksum)
        self.assertEqual('active', image.status)
        self.assertEqual(123, image.virtual_size)
        # If the image already had virtual_size set (i.e. we're setting
        # a new location), we should not re-calculate the value.
        mock_gi.assert_not_called()

    def test_image_set_data_location_metadata(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        loc_meta = {'key': 'value5032'}
        store_api = unit_test_utils.FakeStoreAPI(store_metadata=loc_meta)
        store_utils = unit_test_utils.FakeStoreUtils(store_api)
        image = glance.location.ImageProxy(image_stub, context,
                                           store_api, store_utils)
        image.set_data('YYYY', 4)
        self.assertEqual(4, image.size)
        location_data = image.locations[0]
        self.assertEqual(UUID2, location_data['url'])
        self.assertEqual(loc_meta, location_data['metadata'])
        self.assertEqual('Z', image.checksum)
        self.assertEqual('active', image.status)
        image.delete()
        self.assertEqual(image.status, 'deleted')
        self.assertRaises(glance_store.NotFound,
                          self.store_api.get_from_backend,
                          image.locations[0]['url'], {})

    def test_image_set_data_unknown_size(self):
        context = glance.context.RequestContext(user=USER1)
        image_stub = ImageStub(UUID2, status='queued', locations=[])
        image_stub.disk_format = 'iso'
        image = glance.location.ImageProxy(image_stub, context,
                                           self.store_api, self.store_utils)
        image.set_data('YYYY', None)
        self.assertEqual(4, image.size)
        # NOTE(markwash): FakeStore returns image_id for location
        self.assertEqual(UUID2, image.locations[0]['url'])
        self.assertEqual('Z', image.checksum)
        self.assertEqual('active', image.status)
        image.delete()
        self.assertEqual(image.status, 'deleted')
        self.assertRaises(glance_store.NotFound,
                          self.store_api.get_from_backend,
                          image.locations[0]['url'], context={})

    @mock.patch('glance.location.LOG')
    def test_image_set_data_valid_signature(self, mock_log):
        context = glance.context.RequestContext(user=USER1)
        extra_properties = {
            'img_signature_certificate_uuid': 'UUID',
            'img_signature_hash_method': 'METHOD',
            'img_signature_key_type': 'TYPE',
            'img_signature': 'VALID'
        }
        image_stub = ImageStub(UUID2, status='queued',
                               extra_properties=extra_properties)
        self.mock_object(signature_utils, 'get_verifier',
                         unit_test_utils.fake_get_verifier)
        image = glance.location.ImageProxy(image_stub, context,
                                           self.store_api, self.store_utils)
        image.set_data('YYYY', 4)
        self.assertEqual('active', image.status)
        mock_log.info.assert_any_call(
            'Successfully verified signature for image %s',
            UUID2)

    def test_image_set_data_invalid_signature(self):
        context = glance.context.RequestContext(user=USER1)
        extra_properties = {
            'img_signature_certificate_uuid': 'UUID',
            'img_signature_hash_method': 'METHOD',
            'img_signature_key_type': 'TYPE',
            'img_signature': 'INVALID'
        }
        image_stub = ImageStub(UUID2, status='queued',
                               extra_properties=extra_properties)
        self.mock_object(signature_utils, 'get_verifier',
                         unit_test_utils.fake_get_verifier)
        image = glance.location.ImageProxy(image_stub, context,
                                           self.store_api, self.store_utils)
        with mock.patch.object(self.store_api,
                               'delete_from_backend') as mock_delete:
            self.assertRaises(cursive_exception.SignatureVerificationError,
                              image.set_data,
                              'YYYY', 4)
            mock_delete.assert_called()

    def test_image_set_data_invalid_signature_missing_metadata(self):
        context = glance.context.RequestContext(user=USER1)
        extra_properties = {
            'img_signature_hash_method': 'METHOD',
            'img_signature_key_type': 'TYPE',
            'img_signature': 'INVALID'
        }
        image_stub = ImageStub(UUID2, status='queued',
                               extra_properties=extra_properties)
        self.mock_object(signature_utils, 'get_verifier',
                         unit_test_utils.fake_get_verifier)
        image = glance.location.ImageProxy(image_stub, context,
                                           self.store_api, self.store_utils)
        image.set_data('YYYY', 4)
        self.assertEqual(UUID2, image.locations[0]['url'])
        self.assertEqual('Z', image.checksum)
        # Image is still active, since invalid signature was ignored
        self.assertEqual('active', image.status)

    def _add_image(self, context, image_id, data, len):
        image_stub = ImageStub(image_id, status='queued', locations=[])
        image = glance.location.ImageProxy(image_stub, context,
                                           self.store_api, self.store_utils)
        image.set_data(data, len)
        self.assertEqual(len, image.size)
        # NOTE(markwash): FakeStore returns image_id for location
        location = {'url': image_id, 'metadata': {}, 'status': 'active'}
        self.assertEqual([location], image.locations)
        self.assertEqual([location], image_stub.locations)
        self.assertEqual('active', image.status)
        return (image, image_stub)

    def test_image_change_append_invalid_location_uri(self):
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        location_bad = {'url': 'unknown://location', 'metadata': {}}
        self.assertRaises(exception.BadStoreUri,
                          image1.locations.append, location_bad)

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())

    def test_image_change_append_invalid_location_metatdata(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        # Using only one test rule here is enough to make sure
        # 'store.check_location_metadata()' can be triggered
        # in Location proxy layer. Complete test rule for
        # 'store.check_location_metadata()' testing please
        # check below cases within 'TestStoreMetaDataChecker'.
        location_bad = {'url': UUID3, 'metadata': b"a invalid metadata"}

        self.assertRaises(glance_store.BackendException,
                          image1.locations.append, location_bad)

        image1.delete()
        image2.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

    def test_image_change_append_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}, 'status': 'active'}
        location3 = {'url': UUID3, 'metadata': {}, 'status': 'active'}

        image1.locations.append(location3)

        self.assertEqual([location2, location3], image_stub1.locations)
        self.assertEqual([location2, location3], image1.locations)

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image2.delete()

    def test_image_change_pop_location(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}, 'status': 'active'}
        location3 = {'url': UUID3, 'metadata': {}, 'status': 'active'}

        image1.locations.append(location3)

        self.assertEqual([location2, location3], image_stub1.locations)
        self.assertEqual([location2, location3], image1.locations)

        image1.locations.pop()

        self.assertEqual([location2], image_stub1.locations)
        self.assertEqual([location2], image1.locations)

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image2.delete()

    def test_image_change_extend_invalid_locations_uri(self):
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        location_bad = {'url': 'unknown://location', 'metadata': {}}

        self.assertRaises(exception.BadStoreUri,
                          image1.locations.extend, [location_bad])

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())

    def test_image_change_extend_invalid_locations_metadata(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location_bad = {'url': UUID3, 'metadata': b"a invalid metadata"}

        self.assertRaises(glance_store.BackendException,
                          image1.locations.extend, [location_bad])

        image1.delete()
        image2.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

    def test_image_change_extend_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}, 'status': 'active'}
        location3 = {'url': UUID3, 'metadata': {}, 'status': 'active'}

        image1.locations.extend([location3])

        self.assertEqual([location2, location3], image_stub1.locations)
        self.assertEqual([location2, location3], image1.locations)

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image2.delete()

    def test_image_change_remove_location(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}, 'status': 'active'}
        location3 = {'url': UUID3, 'metadata': {}, 'status': 'active'}
        location_bad = {'url': 'unknown://location', 'metadata': {}}

        image1.locations.extend([location3])
        image1.locations.remove(location2)

        self.assertEqual([location3], image_stub1.locations)
        self.assertEqual([location3], image1.locations)
        self.assertRaises(ValueError,
                          image1.locations.remove, location_bad)

        image1.delete()
        image2.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

    def test_image_change_delete_location(self):
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        del image1.locations[0]

        self.assertEqual([], image_stub1.locations)
        self.assertEqual(0, len(image1.locations))

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())

        image1.delete()

    def test_image_change_insert_invalid_location_uri(self):
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        location_bad = {'url': 'unknown://location', 'metadata': {}}
        self.assertRaises(exception.BadStoreUri,
                          image1.locations.insert, 0, location_bad)

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())

    def test_image_change_insert_invalid_location_metadata(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location_bad = {'url': UUID3, 'metadata': b"a invalid metadata"}

        self.assertRaises(glance_store.BackendException,
                          image1.locations.insert, 0, location_bad)

        image1.delete()
        image2.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

    def test_image_change_insert_location(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}, 'status': 'active'}
        location3 = {'url': UUID3, 'metadata': {}, 'status': 'active'}

        image1.locations.insert(0, location3)

        self.assertEqual([location3, location2], image_stub1.locations)
        self.assertEqual([location3, location2], image1.locations)

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image2.delete()

    def test_image_change_delete_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image1.locations.insert(0, location3)
        del image1.locations[0:100]

        self.assertEqual([], image_stub1.locations)
        self.assertEqual(0, len(image1.locations))
        self.assertRaises(exception.BadStoreUri,
                          image1.locations.insert, 0, location2)
        self.assertRaises(exception.BadStoreUri,
                          image2.locations.insert, 0, location3)

        image1.delete()
        image2.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

    def test_image_change_adding_invalid_location_uri(self):
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        image_stub1 = ImageStub('fake_image_id', status='queued', locations=[])
        image1 = glance.location.ImageProxy(image_stub1, context,
                                            self.store_api, self.store_utils)

        location_bad = {'url': 'unknown://location', 'metadata': {}}

        self.assertRaises(exception.BadStoreUri,
                          image1.locations.__iadd__, [location_bad])
        self.assertEqual([], image_stub1.locations)
        self.assertEqual([], image1.locations)

        image1.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())

    def test_image_change_adding_invalid_location_metadata(self):
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)

        image_stub2 = ImageStub('fake_image_id', status='queued', locations=[])
        image2 = glance.location.ImageProxy(image_stub2, context,
                                            self.store_api, self.store_utils)

        location_bad = {'url': UUID2, 'metadata': b"a invalid metadata"}

        self.assertRaises(glance_store.BackendException,
                          image2.locations.__iadd__, [location_bad])
        self.assertEqual([], image_stub2.locations)
        self.assertEqual([], image2.locations)

        image1.delete()
        image2.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())

    def test_image_change_adding_locations(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.location.ImageProxy(image_stub3, context,
                                            self.store_api, self.store_utils)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}
        with mock.patch("glance.location.store") as mock_store:
            mock_store.get_size_from_uri_and_backend.return_value = 4
            image3.locations += [location2, location3]

        self.assertEqual([location2, location3], image_stub3.locations)
        self.assertEqual([location2, location3], image3.locations)

        image3.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_get_location_index(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)
        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])

        image3 = glance.location.ImageProxy(image_stub3, context,
                                            self.store_api, self.store_utils)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        with mock.patch("glance.location.store") as mock_store:
            mock_store.get_size_from_uri_and_backend.return_value = 4
            image3.locations += [location2, location3]

        self.assertEqual(1, image_stub3.locations.index(location3))

        image3.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_get_location_by_index(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)
        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.location.ImageProxy(image_stub3, context,
                                            self.store_api, self.store_utils)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        with mock.patch("glance.location.store") as mock_store:
            mock_store.get_size_from_uri_and_backend.return_value = 4
            image3.locations += [location2, location3]

        self.assertEqual(1, image_stub3.locations.index(location3))
        self.assertEqual(location2, image_stub3.locations[0])

        image3.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_checking_location_exists(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.location.ImageProxy(image_stub3, context,
                                            self.store_api, self.store_utils)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}
        location_bad = {'url': 'unknown://location', 'metadata': {}}

        with mock.patch("glance.location.store") as mock_store:
            mock_store.get_size_from_uri_and_backend.return_value = 4
            image3.locations += [location2, location3]

        self.assertIn(location3, image_stub3.locations)
        self.assertNotIn(location_bad, image_stub3.locations)

        image3.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image1.delete()
        image2.delete()

    def test_image_reverse_locations_order(self):
        UUID3 = 'a8a61ec4-d7a3-11e2-8c28-000c29c27581'
        self.assertEqual(2, len(self.store_api.data.keys()))

        context = glance.context.RequestContext(user=USER1)
        (image1, image_stub1) = self._add_image(context, UUID2, 'XXXX', 4)
        (image2, image_stub2) = self._add_image(context, UUID3, 'YYYY', 4)

        location2 = {'url': UUID2, 'metadata': {}}
        location3 = {'url': UUID3, 'metadata': {}}

        image_stub3 = ImageStub('fake_image_id', status='queued', locations=[])
        image3 = glance.location.ImageProxy(image_stub3, context,
                                            self.store_api, self.store_utils)
        with mock.patch("glance.location.store") as mock_store:
            mock_store.get_size_from_uri_and_backend.return_value = 4
            image3.locations += [location2, location3]

        image_stub3.locations.reverse()

        self.assertEqual([location3, location2], image_stub3.locations)
        self.assertEqual([location3, location2], image3.locations)

        image3.delete()

        self.assertEqual(2, len(self.store_api.data.keys()))
        self.assertNotIn(UUID2, self.store_api.data.keys())
        self.assertNotIn(UUID3, self.store_api.data.keys())

        image1.delete()
        image2.delete()


class TestStoreImageRepo(utils.BaseTestCase):
    def setUp(self):
        super(TestStoreImageRepo, self).setUp()
        self.store_api = unit_test_utils.FakeStoreAPI()
        store_utils = unit_test_utils.FakeStoreUtils(self.store_api)
        self.image_stub = ImageStub(UUID1)
        self.image = glance.location.ImageProxy(self.image_stub, {},
                                                self.store_api, store_utils)
        self.image_repo_stub = ImageRepoStub()
        self.image_repo = glance.location.ImageRepoProxy(self.image_repo_stub,
                                                         {}, self.store_api,
                                                         store_utils)
        patcher = mock.patch("glance.location._get_member_repo_for_store",
                             self.get_fake_member_repo)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fake_member_repo = FakeMemberRepo(self.image, [TENANT1, TENANT2])
        self.image_member_repo = glance.location.ImageMemberRepoProxy(
            self.fake_member_repo,
            self.image,
            {}, self.store_api)

    def get_fake_member_repo(self, image, context, db_api, store_api):
        return FakeMemberRepo(self.image, [TENANT1, TENANT2])

    def test_add_updates_acls(self):
        self.image_stub.locations = [{'url': 'foo', 'metadata': {},
                                      'status': 'active'},
                                     {'url': 'bar', 'metadata': {},
                                      'status': 'active'}]
        self.image_stub.visibility = 'public'
        self.image_repo.add(self.image)
        self.assertTrue(self.store_api.acls['foo']['public'])
        self.assertEqual([], self.store_api.acls['foo']['read'])
        self.assertEqual([], self.store_api.acls['foo']['write'])
        self.assertTrue(self.store_api.acls['bar']['public'])
        self.assertEqual([], self.store_api.acls['bar']['read'])
        self.assertEqual([], self.store_api.acls['bar']['write'])

    def test_add_ignores_acls_if_no_locations(self):
        self.image_stub.locations = []
        self.image_stub.visibility = 'public'
        self.image_repo.add(self.image)
        self.assertEqual(0, len(self.store_api.acls))

    def test_save_updates_acls(self):
        self.image_stub.locations = [{'url': 'foo', 'metadata': {},
                                      'status': 'active'}]
        self.image_repo.save(self.image)
        self.assertIn('foo', self.store_api.acls)

    def test_add_fetches_members_if_private(self):
        self.image_stub.locations = [{'url': 'glue', 'metadata': {},
                                      'status': 'active'}]
        self.image_stub.visibility = 'private'
        self.image_repo.add(self.image)
        self.assertIn('glue', self.store_api.acls)
        acls = self.store_api.acls['glue']
        self.assertFalse(acls['public'])
        self.assertEqual([], acls['write'])
        self.assertEqual([TENANT1, TENANT2], acls['read'])

    def test_save_fetches_members_if_private(self):
        self.image_stub.locations = [{'url': 'glue', 'metadata': {},
                                      'status': 'active'}]
        self.image_stub.visibility = 'private'
        self.image_repo.save(self.image)
        self.assertIn('glue', self.store_api.acls)
        acls = self.store_api.acls['glue']
        self.assertFalse(acls['public'])
        self.assertEqual([], acls['write'])
        self.assertEqual([TENANT1, TENANT2], acls['read'])

    def test_member_addition_updates_acls(self):
        self.image_stub.locations = [{'url': 'glug', 'metadata': {},
                                      'status': 'active'}]
        self.image_stub.visibility = 'private'
        membership = glance.domain.ImageMembership(
            UUID1, TENANT3, None, None, status='accepted')
        self.image_member_repo.add(membership)
        self.assertIn('glug', self.store_api.acls)
        acls = self.store_api.acls['glug']
        self.assertFalse(acls['public'])
        self.assertEqual([], acls['write'])
        self.assertEqual([TENANT1, TENANT2, TENANT3], acls['read'])

    def test_member_removal_updates_acls(self):
        self.image_stub.locations = [{'url': 'glug', 'metadata': {},
                                      'status': 'active'}]
        self.image_stub.visibility = 'private'
        membership = glance.domain.ImageMembership(
            UUID1, TENANT1, None, None, status='accepted')
        self.image_member_repo.remove(membership)
        self.assertIn('glug', self.store_api.acls)
        acls = self.store_api.acls['glug']
        self.assertFalse(acls['public'])
        self.assertEqual([], acls['write'])
        self.assertEqual([TENANT2], acls['read'])


class TestImageFactory(unit_test_base.StoreClearingUnitTest):

    def setUp(self):
        super(TestImageFactory, self).setUp()
        store_api = unit_test_utils.FakeStoreAPI()
        store_utils = unit_test_utils.FakeStoreUtils(store_api)
        self.image_factory = glance.location.ImageFactoryProxy(
            ImageFactoryStub(),
            glance.context.RequestContext(user=USER1),
            store_api,
            store_utils)

    def test_new_image(self):
        image = self.image_factory.new_image()
        self.assertIsNone(image.image_id)
        self.assertIsNone(image.status)
        self.assertEqual('private', image.visibility)
        self.assertEqual([], image.locations)

    def test_new_image_with_location(self):
        locations = [{'url': '%s/%s' % (BASE_URI, UUID1),
                      'metadata': {}}]
        image = self.image_factory.new_image(locations=locations)
        self.assertEqual(locations, image.locations)
        location_bad = {'url': 'unknown://location', 'metadata': {}}
        self.assertRaises(exception.BadStoreUri,
                          self.image_factory.new_image,
                          locations=[location_bad])


class TestStoreMetaDataChecker(utils.BaseTestCase):

    def test_empty(self):
        glance_store.check_location_metadata({})

    def test_unicode(self):
        m = {'key': 'somevalue'}
        glance_store.check_location_metadata(m)

    def test_unicode_list(self):
        m = {'key': ['somevalue', '2']}
        glance_store.check_location_metadata(m)

    def test_unicode_dict(self):
        inner = {'key1': 'somevalue', 'key2': 'somevalue'}
        m = {'topkey': inner}
        glance_store.check_location_metadata(m)

    def test_unicode_dict_list(self):
        inner = {'key1': 'somevalue', 'key2': 'somevalue'}
        m = {'topkey': inner, 'list': ['somevalue', '2'], 'u': '2'}
        glance_store.check_location_metadata(m)

    def test_nested_dict(self):
        inner = {'key1': 'somevalue', 'key2': 'somevalue'}
        inner = {'newkey': inner}
        inner = {'anotherkey': inner}
        m = {'topkey': inner}
        glance_store.check_location_metadata(m)

    def test_simple_bad(self):
        m = {'key1': object()}
        self.assertRaises(glance_store.BackendException,
                          glance_store.check_location_metadata,
                          m)

    def test_list_bad(self):
        m = {'key1': ['somevalue', object()]}
        self.assertRaises(glance_store.BackendException,
                          glance_store.check_location_metadata,
                          m)

    def test_nested_dict_bad(self):
        inner = {'key1': 'somevalue', 'key2': object()}
        inner = {'newkey': inner}
        inner = {'anotherkey': inner}
        m = {'topkey': inner}

        self.assertRaises(glance_store.BackendException,
                          glance_store.check_location_metadata,
                          m)
