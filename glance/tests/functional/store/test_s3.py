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
"""
Functional tests for the S3 store interface

Set the GLANCE_TEST_S3_CONF environment variable to the location
of a Glance config that defines how to connect to a functional
S3 backend
"""

import ConfigParser
import os
import os.path

import oslo.config.cfg
import six.moves.urllib.parse as urlparse
import testtools

import glance.store.s3
import glance.tests.functional.store as store_tests

try:
    from boto.s3.connection import S3Connection
except ImportError:
    S3Connection = None


def read_config(path):
    cp = ConfigParser.RawConfigParser()
    cp.read(path)
    return cp


def parse_config(config):
    out = {}
    options = [
        's3_store_host',
        's3_store_access_key',
        's3_store_secret_key',
        's3_store_bucket',
        's3_store_bucket_url_format',
    ]

    for option in options:
        out[option] = config.defaults()[option]

    return out


def s3_connect(s3_host, access_key, secret_key, calling_format):
    return S3Connection(access_key, secret_key, host=s3_host,
                        is_secure=False, calling_format=calling_format)


def s3_put_object(s3_client, bucket_name, object_name, contents):
    bucket = s3_client.get_bucket(bucket_name)
    key = bucket.new_key(object_name)
    key.set_contents_from_string(contents)


class TestS3Store(store_tests.BaseTestCase, testtools.TestCase):

    store_cls_path = 'glance.store.s3.Store'
    store_cls = glance.store.s3.Store
    store_name = 's3'

    def setUp(self):
        config_path = os.environ.get('GLANCE_TEST_S3_CONF')
        if not config_path:
            msg = "GLANCE_TEST_S3_CONF environ not set."
            self.skipTest(msg)

        oslo.config.cfg.CONF(args=[], default_config_files=[config_path])

        raw_config = read_config(config_path)
        config = parse_config(raw_config)

        calling_format = glance.store.s3.get_calling_format(
            config['s3_store_bucket_url_format'])

        s3_client = s3_connect(config['s3_store_host'],
                               config['s3_store_access_key'],
                               config['s3_store_secret_key'],
                               calling_format)

        #NOTE(bcwaldon): ensure we have a functional S3 connection
        s3_client.get_all_buckets()

        self.s3_client = s3_client
        self.s3_config = config

        super(TestS3Store, self).setUp()

    def get_store(self, **kwargs):
        store = glance.store.s3.Store(context=kwargs.get('context'))
        store.configure()
        store.configure_add()
        return store

    def stash_image(self, image_id, image_data):
        bucket_name = self.s3_config['s3_store_bucket']
        s3_put_object(self.s3_client, bucket_name, image_id, 'XXX')

        s3_store_host = urlparse.urlparse(self.s3_config['s3_store_host'])
        access_key = urlparse.quote(self.s3_config['s3_store_access_key'])
        secret_key = self.s3_config['s3_store_secret_key']
        auth_chunk = '%s:%s' % (access_key, secret_key)
        netloc = '%s@%s' % (auth_chunk, s3_store_host.netloc)
        path = os.path.join(s3_store_host.path, bucket_name, image_id)

        # This is an s3 url with /<BUCKET>/<OBJECT> on the end
        return 's3://%s%s' % (netloc, path)
