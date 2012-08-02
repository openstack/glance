# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2012 Michael Still and Canonical Inc
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

import copy
import imp
import json
import os
import StringIO
import sys

from glance.tests import utils as test_utils


TOPDIR = os.path.normpath(os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            os.pardir,
                            os.pardir,
                            os.pardir))
GLANCE_REPLICATOR_PATH = os.path.join(TOPDIR, 'bin', 'glance-replicator')

sys.dont_write_bytecode = True
glance_replicator = imp.load_source('glance_replicator',
                                    GLANCE_REPLICATOR_PATH)
sys.dont_write_bytecode = False


IMG_RESPONSE_ACTIVE = {'content-length': '0',
                       'property-image_state': 'available',
                       'min_ram': '0',
                       'disk_format': 'aki',
                       'updated_at': '2012-06-25T02:10:36',
                       'date': 'Thu, 28 Jun 2012 07:20:05 GMT',
                       'owner': '8aef75b5c0074a59aa99188fdb4b9e90',
                       'id': '6d55dd55-053a-4765-b7bc-b30df0ea3861',
                       'size': '4660272',
                       'property-image_location':
                           ('ubuntu-bucket/oneiric-server-cloudimg-amd64-'
                            'vmlinuz-generic.manifest.xml'),
                       'property-architecture': 'x86_64',
                       'etag': 'f46cfe7fb3acaff49a3567031b9b53bb',
                       'location':
                           ('http://127.0.0.1:9292/v1/images/'
                            '6d55dd55-053a-4765-b7bc-b30df0ea3861'),
                       'container_format': 'aki',
                       'status': 'active',
                       'deleted': 'False',
                       'min_disk': '0',
                       'is_public': 'False',
                       'name':
                           ('ubuntu-bucket/oneiric-server-cloudimg-amd64-'
                            'vmlinuz-generic'),
                       'checksum': 'f46cfe7fb3acaff49a3567031b9b53bb',
                       'created_at': '2012-06-25T02:10:32',
                       'protected': 'False',
                       'content-type': 'text/html; charset=UTF-8'
                       }

IMG_RESPONSE_QUEUED = copy.copy(IMG_RESPONSE_ACTIVE)
IMG_RESPONSE_QUEUED['status'] = 'queued'
IMG_RESPONSE_QUEUED['id'] = '49b2c782-ee10-4692-84f8-3942e9432c4b'
IMG_RESPONSE_QUEUED['location'] = ('http://127.0.0.1:9292/v1/images/'
                                   + IMG_RESPONSE_QUEUED['id'])


class FakeHTTPConnection(object):
    def __init__(self):
        self.count = 0
        self.reqs = {}
        self.last_req = None
        self.host = 'localhost'
        self.port = 9292

    def prime_request(self, method, url, in_body, in_headers,
                      out_body, out_headers):
        if not url.startswith('/'):
            url = '/' + url

        hkeys = in_headers.keys()
        hkeys.sort()
        hashable = (method, url, in_body, ' '.join(hkeys))

        flat_headers = []
        for key in out_headers:
            flat_headers.append((key, out_headers[key]))

        self.reqs[hashable] = (out_body, flat_headers)

    def request(self, method, url, body, headers):
        self.count += 1

        hkeys = headers.keys()
        hkeys.sort()
        hashable = (method, url, body, ' '.join(hkeys))

        if not hashable in self.reqs:
            options = []
            for h in self.reqs:
                options.append(repr(h))

            raise Exception('No such primed request: %s "%s"\n'
                            '%s\n\n'
                            'Available:\n'
                            '%s'
                            % (method, url, hashable, '\n\n'.join(options)))
        self.last_req = hashable

    def getresponse(self):
        class FakeResponse(object):
            def __init__(self, (body, headers)):
                self.body = StringIO.StringIO(body)
                self.headers = headers
                self.status = 200

            def read(self, count=1000000):
                return self.body.read(count)

            def getheaders(self):
                return self.headers

        return FakeResponse(self.reqs[self.last_req])


class ImageServiceTestCase(test_utils.BaseTestCase):
    def test_rest_get_images(self):
        c = glance_replicator.ImageService(FakeHTTPConnection(), 'noauth')

        # Two images, one of which is queued
        resp = {'images': [IMG_RESPONSE_ACTIVE, IMG_RESPONSE_QUEUED]}
        c.conn.prime_request('GET', 'v1/images/detail?is_public=None', '',
                             {'x-auth-token': 'noauth'},
                             json.dumps(resp), {})
        c.conn.prime_request('GET',
                             ('v1/images/detail?marker=%s&is_public=None'
                              % IMG_RESPONSE_QUEUED['id']),
                             '', {'x-auth-token': 'noauth'},
                             json.dumps({'images': []}), {})

        imgs = list(c.get_images())
        self.assertEquals(len(imgs), 2)
        self.assertEquals(c.conn.count, 2)

    def test_rest_get_image(self):
        c = glance_replicator.ImageService(FakeHTTPConnection(), 'noauth')

        image_contents = 'THISISTHEIMAGEBODY'
        c.conn.prime_request('GET',
                             'v1/images/%s' % IMG_RESPONSE_ACTIVE['id'],
                             '', {'x-auth-token': 'noauth'},
                             image_contents, IMG_RESPONSE_ACTIVE)

        body = c.get_image(IMG_RESPONSE_ACTIVE['id'])
        self.assertEquals(body.read(), image_contents)

    def test_rest_header_list_to_dict(self):
        i = [('x-image-meta-banana', 42), ('gerkin', 12)]
        o = glance_replicator.ImageService._header_list_to_dict(i)
        self.assertTrue('banana' in o)
        self.assertTrue('gerkin' in o)
        self.assertFalse('x-image-meta-banana' in o)

    def test_rest_get_image_meta(self):
        c = glance_replicator.ImageService(FakeHTTPConnection(), 'noauth')

        c.conn.prime_request('HEAD',
                             'v1/images/%s' % IMG_RESPONSE_ACTIVE['id'],
                             '', {'x-auth-token': 'noauth'},
                             '', IMG_RESPONSE_ACTIVE)

        header = c.get_image_meta(IMG_RESPONSE_ACTIVE['id'])
        self.assertTrue('id' in header)

    def test_rest_dict_to_headers(self):
        i = {'banana': 42,
             'gerkin': 12}
        o = glance_replicator.ImageService._dict_to_headers(i)
        self.assertTrue('x-image-meta-banana' in o)
        self.assertTrue('x-image-meta-gerkin' in o)

    def test_rest_add_image(self):
        c = glance_replicator.ImageService(FakeHTTPConnection(), 'noauth')

        image_body = 'THISISANIMAGEBODYFORSURE!'
        image_meta_with_proto = {}
        image_meta_with_proto['x-auth-token'] = 'noauth'
        image_meta_with_proto['Content-Type'] = 'application/octet-stream'
        image_meta_with_proto['Content-Length'] = len(image_body)

        for key in IMG_RESPONSE_ACTIVE:
            image_meta_with_proto['x-image-meta-%s' % key] = \
                IMG_RESPONSE_ACTIVE[key]

        c.conn.prime_request('POST', 'v1/images',
                             image_body, image_meta_with_proto,
                             '', IMG_RESPONSE_ACTIVE)

        headers, body = c.add_image(IMG_RESPONSE_ACTIVE, image_body)
        self.assertEquals(headers, IMG_RESPONSE_ACTIVE)
        self.assertEquals(c.conn.count, 1)
