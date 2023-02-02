# Copyright 2012 OpenStack Foundation.
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
import glance_store as store
from unittest import mock
import urllib

from oslo_config import cfg
from oslo_policy import policy

from glance.async_.flows._internal_plugins import base_download
from glance.common import exception
from glance.common import store_utils
from glance.common import wsgi
import glance.context
import glance.db.simple.api as simple_db


CONF = cfg.CONF

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'

USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
USER2 = '0b3b3006-cb76-4517-ae32-51397e22c754'
USER3 = '2hss8dkl-d8jh-88yd-uhs9-879sdjsd8skd'

BASE_URI = 'http://storeurl.com/container'


def sort_url_by_qs_keys(url):
    # NOTE(kragniz): this only sorts the keys of the query string of a url.
    # For example, an input of '/v2/tasks?sort_key=id&sort_dir=asc&limit=10'
    # returns '/v2/tasks?limit=10&sort_dir=asc&sort_key=id'. This is to prevent
    # non-deterministic ordering of the query string causing problems with unit
    # tests.

    parsed = urllib.parse.urlparse(url)
    queries = urllib.parse.parse_qsl(parsed.query, True)
    sorted_query = sorted(queries, key=lambda x: x[0])

    encoded_sorted_query = urllib.parse.urlencode(sorted_query, True)

    url_parts = (parsed.scheme, parsed.netloc, parsed.path,
                 parsed.params, encoded_sorted_query,
                 parsed.fragment)

    return urllib.parse.urlunparse(url_parts)


def get_fake_request(path='', method='POST', is_admin=False, user=USER1,
                     roles=None, headers=None, tenant=TENANT1):
    if roles is None:
        roles = ['member', 'reader']

    req = wsgi.Request.blank(path)
    req.method = method
    req.headers = {'x-openstack-request-id': 'my-req'}

    if headers is not None:
        req.headers.update(headers)

    kwargs = {
        'user': user,
        'tenant': tenant,
        'roles': roles,
        'is_admin': is_admin,
    }

    req.context = glance.context.RequestContext(**kwargs)
    return req


def enforcer_from_rules(unparsed_rules):
    rules = policy.Rules.from_dict(unparsed_rules)
    enforcer = glance.api.policy.Enforcer(
        suppress_deprecation_warnings=True)
    enforcer.set_rules(rules, overwrite=True)
    return enforcer


def fake_get_size_from_backend(uri, context=None):
    return 1


def fake_get_verifier(context, img_signature_certificate_uuid,
                      img_signature_hash_method, img_signature,
                      img_signature_key_type):
    verifier = mock.Mock()
    if (img_signature is not None and img_signature == 'VALID'):
        verifier.verify.return_value = None
    else:
        ex = crypto_exception.InvalidSignature()
        verifier.verify.side_effect = ex
    return verifier


def get_fake_context(user=USER1, tenant=TENANT1, roles=None, is_admin=False):
    if roles is None:
        roles = ['member']

    kwargs = {
        'user': user,
        'tenant': tenant,
        'roles': roles,
        'is_admin': is_admin,
    }

    context = glance.context.RequestContext(**kwargs)
    return context


class FakeDB(object):

    def __init__(self, initialize=True):
        self.reset()
        if initialize:
            self.init_db()

    @staticmethod
    def init_db():
        images = [
            {'id': UUID1, 'owner': TENANT1, 'status': 'queued',
             'locations': [{'url': '%s/%s' % (BASE_URI, UUID1),
                            'metadata': {}, 'status': 'queued'}],
             'disk_format': 'raw', 'container_format': 'bare'},
            {'id': UUID2, 'owner': TENANT1, 'status': 'queued',
             'disk_format': 'raw', 'container_format': 'bare'},
        ]
        [simple_db.image_create(None, image) for image in images]

        members = [
            {'image_id': UUID1, 'member': TENANT1, 'can_share': True},
            {'image_id': UUID1, 'member': TENANT2, 'can_share': False},
        ]
        [simple_db.image_member_create(None, member) for member in members]

        simple_db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    @staticmethod
    def reset():
        simple_db.reset()

    def __getattr__(self, key):
        return getattr(simple_db, key)


class FakeStoreUtils(object):
    def __init__(self, store_api):
        self.store_api = store_api

    def safe_delete_from_backend(self, context, id, location):
        try:
            del self.store_api.data[location['url']]
        except KeyError:
            pass

    def schedule_delayed_delete_from_backend(self, context, id, location):
        pass

    def delete_image_location_from_backend(self, context,
                                           image_id, location):
        if CONF.delayed_delete:
            self.schedule_delayed_delete_from_backend(context, image_id,
                                                      location)
        else:
            self.safe_delete_from_backend(context, image_id, location)

    def validate_external_location(self, uri):
        if uri and urllib.parse.urlparse(uri).scheme:
            return store_utils.validate_external_location(uri)
        else:
            return True


class FakeStoreAPI(object):
    def __init__(self, store_metadata=None):
        self.data = {
            '%s/%s' % (BASE_URI, UUID1): ('XXX', 3),
            '%s/fake_location' % (BASE_URI): ('YYY', 3)
        }
        self.acls = {}
        if store_metadata is None:
            self.store_metadata = {}
        else:
            self.store_metadata = store_metadata

    def create_stores(self):
        pass

    def set_acls(self, uri, public=False, read_tenants=None,
                 write_tenants=None, context=None):
        if read_tenants is None:
            read_tenants = []
        if write_tenants is None:
            write_tenants = []

        self.acls[uri] = {
            'public': public,
            'read': read_tenants,
            'write': write_tenants,
        }

    def get_from_backend(self, location, offset=0,
                         chunk_size=None, context=None):
        try:
            scheme = location[:location.find('/') - 1]
            if scheme == 'unknown':
                raise store.UnknownScheme(scheme=scheme)
            return self.data[location]
        except KeyError:
            raise store.NotFound(image=location)

    def get_size_from_backend(self, location, context=None):
        return self.get_from_backend(location, context=context)[1]

    def add_to_backend(self, conf, image_id, data, size,
                       scheme=None, context=None, verifier=None):
        store_max_size = 7
        current_store_size = 2
        for location in self.data.keys():
            if image_id in location:
                raise exception.Duplicate()
        if not size:
            # 'data' is a string wrapped in a LimitingReader|CooperativeReader
            # pipeline, so peek under the hood of those objects to get at the
            # string itself.
            size = len(data.data.fd)
        if (current_store_size + size) > store_max_size:
            raise exception.StorageFull()
        if context.user_id == USER2:
            raise exception.Forbidden()
        if context.user_id == USER3:
            raise exception.StorageWriteDenied()
        self.data[image_id] = (data, size)
        checksum = 'Z'
        return (image_id, size, checksum, self.store_metadata)

    def add_to_backend_with_multihash(
            self, conf, image_id, data, size, hashing_algo,
            scheme=None, context=None, verifier=None):
        store_max_size = 7
        current_store_size = 2
        for location in self.data.keys():
            if image_id in location:
                raise exception.Duplicate()
        if not size:
            # 'data' is a string wrapped in a LimitingReader|CooperativeReader
            # pipeline, so peek under the hood of those objects to get at the
            # string itself.
            size = len(data.data.fd)
        if (current_store_size + size) > store_max_size:
            raise exception.StorageFull()
        if context.user_id == USER2:
            raise exception.Forbidden()
        if context.user_id == USER3:
            raise exception.StorageWriteDenied()
        self.data[image_id] = (data, size)
        checksum = 'Z'
        multihash = 'ZZ'
        return (image_id, size, checksum, multihash, self.store_metadata)

    def check_location_metadata(self, val, key=''):
        store.check_location_metadata(val)

    def delete_from_backend(self, uri, context=None):
        pass


class FakeStoreAPIReader(FakeStoreAPI):
    """A store API that actually reads from the data pipe."""

    def add_to_backend_with_multihash(self, conf, image_id, data, size,
                                      hashing_algo, scheme=None, context=None,
                                      verifier=None):
        for chunk in data:
            pass

        return super(FakeStoreAPIReader, self).add_to_backend_with_multihash(
            conf, image_id, data, size, hashing_algo,
            scheme=scheme, context=context, verifier=verifier)


class FakePolicyEnforcer(object):
    def __init__(self, *_args, **kwargs):
        self.rules = {}

    def enforce(self, _ctxt, action, target=None, **kwargs):
        """Raise Forbidden if a rule for given action is set to false."""
        if self.rules.get(action) is False:
            raise exception.Forbidden()

    def set_rules(self, rules):
        self.rules = rules


class FakeNotifier(object):
    def __init__(self, *_args, **kwargs):
        self.log = []

    def _notify(self, event_type, payload, level):
        log = {
            'notification_type': level,
            'event_type': event_type,
            'payload': payload
        }
        self.log.append(log)

    def warn(self, event_type, payload):
        self._notify(event_type, payload, 'WARN')

    def info(self, event_type, payload):
        self._notify(event_type, payload, 'INFO')

    def error(self, event_type, payload):
        self._notify(event_type, payload, 'ERROR')

    def debug(self, event_type, payload):
        self._notify(event_type, payload, 'DEBUG')

    def critical(self, event_type, payload):
        self._notify(event_type, payload, 'CRITICAL')

    def get_logs(self):
        return self.log


class FakeGateway(object):
    def __init__(self, image_factory=None, image_member_factory=None,
                 image_repo=None, task_factory=None, task_repo=None):
        self.image_factory = image_factory
        self.image_member_factory = image_member_factory
        self.image_repo = image_repo
        self.task_factory = task_factory
        self.task_repo = task_repo

    def get_image_factory(self, context):
        return self.image_factory

    def get_image_member_factory(self, context):
        return self.image_member_factory

    def get_repo(self, context):
        return self.image_repo

    def get_task_factory(self, context):
        return self.task_factory

    def get_task_repo(self, context):
        return self.task_repo


class FakeTask(object):
    def __init__(self, task_id, type=None, status=None):
        self.task_id = task_id
        self.type = type
        self.message = None
        self.input = None
        self._status = status
        self._executor = None

    def success(self, result):
        self.result = result
        self._status = 'success'

    def fail(self, message):
        self.message = message
        self._status = 'failure'


class FakeBaseDownloadPlugin(base_download.BaseDownload):
    def execute(self):
        pass
