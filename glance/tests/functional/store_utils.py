# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
# Copyright 2012 Red Hat, Inc
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
Utility methods to set testcases up for Swift and/or S3 tests.
"""

import BaseHTTPServer
import ConfigParser
import httplib
import os
import random
import thread

from glance.store.s3 import get_s3_location, get_calling_format


FIVE_KB = 5 * 1024


class RemoteImageHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_HEAD(self):
        """
        Respond to an image HEAD request fake metadata
        """
        if 'images' in self.path:
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', FIVE_KB)
            self.end_headers()
            return
        else:
            self.send_error(404, 'File Not Found: %s' % self.path)
            return

    def do_GET(self):
        """
        Respond to an image GET request with fake image content.
        """
        if 'images' in self.path:
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', FIVE_KB)
            self.end_headers()
            image_data = '*' * FIVE_KB
            self.wfile.write(image_data)
            self.wfile.close()
            return
        else:
            self.send_error(404, 'File Not Found: %s' % self.path)
            return

    def log_message(self, format, *args):
        """
        Simple override to prevent writing crap to stderr...
        """
        pass


def setup_http(test):
    server_class = BaseHTTPServer.HTTPServer
    remote_server = server_class(('127.0.0.1', 0), RemoteImageHandler)
    remote_ip, remote_port = remote_server.server_address

    def serve_requests(httpd):
        httpd.serve_forever()

    thread.start_new_thread(serve_requests, (remote_server,))
    test.http_server = remote_server
    test.http_ip = remote_ip
    test.http_port = remote_port


def teardown_http(test):
    if test.http_server:
        test.http_server.shutdown()


def get_http_uri(test, image_id):
    uri = 'http://%(http_ip)s:%(http_port)d/images/' % test.__dict__
    uri += image_id
    return uri


def _uniq(value):
    return '%s.%d' % (value, random.randint(0, 99999))


def setup_swift(test):
    # Test machines can set the GLANCE_TEST_SWIFT_CONF variable
    # to override the location of the config file for migration testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_SWIFT_CONF')

    if not CONFIG_FILE_PATH:
        test.disabled_message = "GLANCE_TEST_SWIFT_CONF environ not set."
        print "GLANCE_TEST_SWIFT_CONF environ not set."
        test.disabled = True
        return

    if os.path.exists(CONFIG_FILE_PATH):
        cp = ConfigParser.RawConfigParser()
        try:
            cp.read(CONFIG_FILE_PATH)
            defaults = cp.defaults()
            for key, value in defaults.items():
                if key == 'swift_store_container':
                    test.__dict__[key] = (_uniq(value))
                else:
                    test.__dict__[key] = value

        except ConfigParser.ParsingError, e:
            test.disabled_message = ("Failed to read test_swift.conf "
                                     "file. Got error: %s" % e)
            test.disabled = True
            return

    import swiftclient

    try:
        swift_host = test.swift_store_auth_address
        if not swift_host.startswith('http'):
            swift_host = 'https://' + swift_host
        user = test.swift_store_user
        key = test.swift_store_key
        container_name = test.swift_store_container
    except AttributeError, e:
        test.disabled_message = ("Failed to find required configuration "
                                 "options for Swift store. "
                                 "Got error: %s" % e)
        test.disabled = True
        return

    swift_conn = swiftclient.Connection(
        authurl=swift_host, user=user, key=key, snet=False, retries=1)

    try:
        _resp_headers, containers = swift_conn.get_account()
    except Exception, e:
        test.disabled_message = ("Failed to get_account from Swift "
                                 "Got error: %s" % e)
        test.disabled = True
        return

    try:
        for container in containers:
            if container == container_name:
                swift_conn.delete_container(container)
    except swiftclient.ClientException, e:
        test.disabled_message = ("Failed to delete container from Swift "
                                 "Got error: %s" % e)
        test.disabled = True
        return

    test.swift_conn = swift_conn

    try:
        swift_conn.put_container(container_name)
    except swiftclient.ClientException, e:
        test.disabled_message = ("Failed to create container. "
                                 "Got error: %s" % e)
        test.disabled = True
        return


def teardown_swift(test):
    if not test.disabled:
        import swiftclient
        try:
            _resp_headers, containers = swift_conn.get_account()
            # Delete all containers matching the container name prefix
            for container in containers:
                if container.find(container_name) == 0:
                    swift_conn.delete_container(container)
        except swiftclient.ClientException, e:
            if e.http_status == httplib.CONFLICT:
                pass
            else:
                raise
        test.swift_conn.put_container(test.swift_store_container)


def get_swift_uri(test, image_id):
    # Apparently we must use HTTPS with Cloud Files now, otherwise
    # we will get a 301 Moved.... :(
    uri = ('swift+https://%(swift_store_user)s:%(swift_store_key)s' %
           test.__dict__)
    uri += ('@%(swift_store_auth_address)s/%(swift_store_container)s/' %
           test.__dict__)
    uri += image_id
    return uri.replace('@http://', '@')


def setup_s3(test):
    # Test machines can set the GLANCE_TEST_S3_CONF variable
    # to override the location of the config file for S3 testing
    CONFIG_FILE_PATH = os.environ.get('GLANCE_TEST_S3_CONF')

    if not CONFIG_FILE_PATH:
        test.disabled_message = "GLANCE_TEST_S3_CONF environ not set."
        test.disabled = True
        return

    if os.path.exists(CONFIG_FILE_PATH):
        cp = ConfigParser.RawConfigParser()
        try:
            cp.read(CONFIG_FILE_PATH)
            defaults = cp.defaults()
            for key, value in defaults.items():
                test.__dict__[key] = (_uniq(value)
                                      if key == 's3_store_bucket' else value)
        except ConfigParser.ParsingError, e:
            test.disabled_message = ("Failed to read test_s3.conf config "
                                     "file. Got error: %s" % e)
            test.disabled = True
            return

    from boto.s3.connection import S3Connection
    from boto.exception import S3ResponseError

    try:
        s3_host = test.s3_store_host
        access_key = test.s3_store_access_key
        secret_key = test.s3_store_secret_key
        bucket_name = test.s3_store_bucket
    except AttributeError, e:
        test.disabled_message = ("Failed to find required configuration "
                                 "options for S3 store. Got error: %s" % e)
        test.disabled = True
        return

    calling_format = get_calling_format(test.s3_store_bucket_url_format)
    s3_conn = S3Connection(access_key, secret_key,
                           host=s3_host,
                           is_secure=False,
                           calling_format=calling_format)

    test.bucket = None
    try:
        buckets = s3_conn.get_all_buckets()
        for bucket in buckets:
            if bucket.name == bucket_name:
                test.bucket = bucket
    except S3ResponseError, e:
        test.disabled_message = ("Failed to connect to S3 with "
                                 "credentials, to find bucket. "
                                 "Got error: %s" % e)
        test.disabled = True
        return
    except TypeError, e:
        # This hack is necessary because of a bug in boto 1.9b:
        # http://code.google.com/p/boto/issues/detail?id=540
        test.disabled_message = ("Failed to connect to S3 with "
                                 "credentials. Got error: %s" % e)
        test.disabled = True
        return

    test.s3_conn = s3_conn

    if not test.bucket:
        location = get_s3_location(test.s3_store_host)
        try:
            test.bucket = s3_conn.create_bucket(bucket_name,
                                                location=location)
        except S3ResponseError, e:
            test.disabled_message = ("Failed to create bucket. "
                                     "Got error: %s" % e)
            test.disabled = True
            return
    else:
        for key in test.bucket.list():
            key.delete()


def teardown_s3(test):
    if not test.disabled:
        # It's not possible to simply clear a bucket. You
        # need to loop over all the keys and delete them
        # all first...
        for key in test.bucket.list():
            key.delete()
        test.s3_conn.delete_bucket(test.s3_store_bucket)


def get_s3_uri(test, image_id):
    uri = ('s3://%(s3_store_access_key)s:%(s3_store_secret_key)s' %
           test.__dict__)
    uri += '@%(s3_conn)s/' % test.__dict__
    uri += '%(s3_store_bucket)s/' % test.__dict__
    uri += image_id
    return uri.replace('S3Connection:', '')
