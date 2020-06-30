# Copyright 2010-2011 OpenStack Foundation
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

"""Stubouts, mocks and fixtures for the test suite"""

import os

try:
    import sendfile
    SENDFILE_SUPPORTED = True
except ImportError:
    SENDFILE_SUPPORTED = False

import routes
import webob

from glance.api.middleware import context
from glance.api.v2 import router
import glance.common.client


DEBUG = False


def stub_out_store_server(stubs, base_dir, **kwargs):
    """Mocks calls to 127.0.0.1 on 9292 for testing.

    Done so that a real Glance server does not need to be up and
    running
    """

    class FakeSocket(object):

        def __init__(self, *args, **kwargs):
            pass

        def fileno(self):
            return 42

    class FakeSendFile(object):

        def __init__(self, req):
            self.req = req

        def sendfile(self, o, i, offset, nbytes):
            os.lseek(i, offset, os.SEEK_SET)
            prev_len = len(self.req.body)
            self.req.body += os.read(i, nbytes)
            return len(self.req.body) - prev_len

    class FakeGlanceConnection(object):

        def __init__(self, *args, **kwargs):
            self.sock = FakeSocket()
            self.stub_force_sendfile = kwargs.get('stub_force_sendfile',
                                                  SENDFILE_SUPPORTED)

        def connect(self):
            return True

        def close(self):
            return True

        def putrequest(self, method, url):
            self.req = webob.Request.blank(url)
            if self.stub_force_sendfile:
                fake_sendfile = FakeSendFile(self.req)
                stubs.Set(sendfile, 'sendfile', fake_sendfile.sendfile)
            self.req.method = method

        def putheader(self, key, value):
            self.req.headers[key] = value

        def endheaders(self):
            hl = [i.lower() for i in self.req.headers.keys()]
            assert not ('content-length' in hl and
                        'transfer-encoding' in hl), (
                'Content-Length and Transfer-Encoding are mutually exclusive')

        def send(self, data):
            # send() is called during chunked-transfer encoding, and
            # data is of the form %x\r\n%s\r\n. Strip off the %x and
            # only write the actual data in tests.
            self.req.body += data.split("\r\n")[1]

        def request(self, method, url, body=None, headers=None):
            self.req = webob.Request.blank(url)
            self.req.method = method
            if headers:
                self.req.headers = headers
            if body:
                self.req.body = body

        def getresponse(self):
            mapper = routes.Mapper()
            api = context.UnauthenticatedContextMiddleware(router.API(mapper))
            res = self.req.get_response(api)

            # httplib.Response has a read() method...fake it out
            def fake_reader():
                return res.body

            setattr(res, 'read', fake_reader)
            return res

    def fake_image_iter(self):
        for i in self.source.app_iter:
            yield i

    def fake_sendable(self, body):
        force = getattr(self, 'stub_force_sendfile', None)
        if force is None:
            return self._stub_orig_sendable(body)
        else:
            if force:
                assert glance.common.client.SENDFILE_SUPPORTED
            return force

    setattr(glance.common.client.BaseClient, '_stub_orig_sendable',
            glance.common.client.BaseClient._sendable)
