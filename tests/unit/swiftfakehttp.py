# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack, LLC
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
fakehttp/socket implementation

- TrackerSocket: an object which masquerades as a socket and responds to
  requests in a manner consistent with a *very* stupid CloudFS tracker.

- CustomHTTPConnection: an object which subclasses httplib.HTTPConnection
  in order to replace it's socket with a TrackerSocket instance.

The unittests each have setup methods which create freerange connection
instances that have had their HTTPConnection instances replaced by
intances of CustomHTTPConnection.
"""

from httplib import HTTPConnection as connbase
import StringIO


class FakeSocket(object):
    def __init__(self):
        self._rbuffer = StringIO.StringIO()
        self._wbuffer = StringIO.StringIO()

    def close(self):
        pass

    def send(self, data, flags=0):
        self._rbuffer.write(data)
    sendall = send

    def recv(self, len=1024, flags=0):
        return self._wbuffer(len)

    def connect(self):
        pass

    def makefile(self, mode, flags):
        return self._wbuffer


class TrackerSocket(FakeSocket):
    def write(self, data):
        self._wbuffer.write(data)

    def read(self, length=-1):
        return self._rbuffer.read(length)

    def _create_GET_account_content(self, path, args):
        if 'format' in args and args['format'] == 'json':
            containers = []
            containers.append('[\n')
            containers.append('{"name":"container1","count":2,"bytes":78},\n')
            containers.append('{"name":"container2","count":1,"bytes":39},\n')
            containers.append('{"name":"container3","count":3,"bytes":117}\n')
            containers.append(']\n')
        elif 'format' in args and args['format'] == 'xml':
            containers = []
            containers.append('<?xml version="1.0" encoding="UTF-8"?>\n')
            containers.append('<account name="FakeAccount">\n')
            containers.append('<container><name>container1</name>'
                              '<count>2</count>'
                              '<bytes>78</bytes></container>\n')
            containers.append('<container><name>container2</name>'
                              '<count>1</count>'
                              '<bytes>39</bytes></container>\n')
            containers.append('<container><name>container3</name>'
                              '<count>3</count>'
                              '<bytes>117</bytes></container>\n')
            containers.append('</account>\n')
        else:
            containers = ['container%s\n' % i for i in range(1, 4)]
        return ''.join(containers)

    def _create_GET_container_content(self, path, args):
        left = 0
        right = 9
        if 'offset' in args:
            left = int(args['offset'])
        if 'limit' in args:
            right = left + int(args['limit'])

        if 'format' in args and args['format'] == 'json':
            objects = []
            objects.append('{"name":"object1",'
                           '"hash":"4281c348eaf83e70ddce0e07221c3d28",'
                           '"bytes":14,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            objects.append('{"name":"object2",'
                           '"hash":"b039efe731ad111bc1b0ef221c3849d0",'
                           '"bytes":64,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            objects.append('{"name":"object3",'
                           '"hash":"4281c348eaf83e70ddce0e07221c3d28",'
                           '"bytes":14,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            objects.append('{"name":"object4",'
                           '"hash":"b039efe731ad111bc1b0ef221c3849d0",'
                           '"bytes":64,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            objects.append('{"name":"object5",'
                           '"hash":"4281c348eaf83e70ddce0e07221c3d28",'
                           '"bytes":14,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            objects.append('{"name":"object6",'
                           '"hash":"b039efe731ad111bc1b0ef221c3849d0",'
                           '"bytes":64,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            objects.append('{"name":"object7",'
                           '"hash":"4281c348eaf83e70ddce0e07221c3d28",'
                           '"bytes":14,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            objects.append('{"name":"object8",'
                           '"hash":"b039efe731ad111bc1b0ef221c3849d0",'
                           '"bytes":64,'
                           '"content_type":"application\/octet-stream",'
                           '"last_modified":"2007-03-04 20:32:17"}')
            output = '[\n%s\n]\n' % (',\n'.join(objects[left:right]))
        elif 'format' in args and args['format'] == 'xml':
            objects = []
            objects.append('<object><name>object1</name>'
                       '<hash>4281c348eaf83e70ddce0e07221c3d28</hash>'
                       '<bytes>14</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects.append('<object><name>object2</name>'
                       '<hash>b039efe731ad111bc1b0ef221c3849d0</hash>'
                       '<bytes>64</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects.append('<object><name>object3</name>'
                       '<hash>4281c348eaf83e70ddce0e07221c3d28</hash>'
                       '<bytes>14</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects.append('<object><name>object4</name>'
                       '<hash>b039efe731ad111bc1b0ef221c3849d0</hash>'
                       '<bytes>64</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects.append('<object><name>object5</name>'
                       '<hash>4281c348eaf83e70ddce0e07221c3d28</hash>'
                       '<bytes>14</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects.append('<object><name>object6</name>'
                       '<hash>b039efe731ad111bc1b0ef221c3849d0</hash>'
                       '<bytes>64</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects.append('<object><name>object7</name>'
                       '<hash>4281c348eaf83e70ddce0e07221c3d28</hash>'
                       '<bytes>14</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects.append('<object><name>object8</name>'
                       '<hash>b039efe731ad111bc1b0ef221c3849d0</hash>'
                       '<bytes>64</bytes>'
                       '<content_type>application/octet-stream</content_type>'
                       '<last_modified>2007-03-04 20:32:17</last_modified>'
                       '</object>\n')
            objects = objects[left:right]
            objects.insert(0, '<?xml version="1.0" encoding="UTF-8"?>\n')
            objects.insert(1, '<container name="test_container_1"\n')
            objects.append('</container>\n')
            output = ''.join(objects)
        else:
            objects = ['object%s\n' % i for i in range(1, 9)]
            objects = objects[left:right]
            output = ''.join(objects)

        # prefix/path don't make much sense given our test data
        if 'prefix' in args or 'path' in args:
            pass
        return output

    def render_GET(self, path, args):
        # Special path that returns 404 Not Found
        if (len(path) == 4) and (path[3] == 'bogus'):
            self.write('HTTP/1.1 404 Not Found\n')
            self.write('Content-Type: text/plain\n')
            self.write('Content-Length: 0\n')
            self.write('Connection: close\n\n')
            return

        self.write('HTTP/1.1 200 Ok\n')
        self.write('Content-Type: text/plain\n')
        if len(path) == 2:
            content = self._create_GET_account_content(path, args)
        elif len(path) == 3:
            content = self._create_GET_container_content(path, args)
        # Object
        elif len(path) == 4:
            content = 'I am a teapot, short and stout\n'
        self.write('Content-Length: %d\n' % len(content))
        self.write('Connection: close\n\n')
        self.write(content)

    def render_HEAD(self, path, args):
        # Account
        if len(path) == 2:
            self.write('HTTP/1.1 204 No Content\n')
            self.write('Content-Type: text/plain\n')
            self.write('Connection: close\n')
            self.write('X-Account-Container-Count: 3\n')
            self.write('X-Account-Bytes-Used: 234\n\n')
        else:
            self.write('HTTP/1.1 200 Ok\n')
            self.write('Content-Type: text/plain\n')
            self.write('ETag: d5c7f3babf6c602a8da902fb301a9f27\n')
            self.write('Content-Length: 21\n')
            self.write('Connection: close\n\n')

    def render_POST(self, path, args):
        self.write('HTTP/1.1 202 Ok\n')
        self.write('Connection: close\n\n')

    def render_PUT(self, path, args):
        self.write('HTTP/1.1 200 Ok\n')
        self.write('Content-Type: text/plain\n')
        self.write('Connection: close\n\n')
    render_DELETE = render_PUT

    def render(self, method, uri):
        if '?' in uri:
            parts = uri.split('?')
            query = parts[1].strip('&').split('&')
            args = dict([tuple(i.split('=', 1)) for i in query])
            path = parts[0].strip('/').split('/')
        else:
            args = {}
            path = uri.strip('/').split('/')

        if hasattr(self, 'render_%s' % method):
            getattr(self, 'render_%s' % method)(path, args)
        else:
            self.write('HTTP/1.1 406 Not Acceptable\n')
            self.write('Content-Type: text/plain\n')
            self.write('Connection: close\n')

    def makefile(self, mode, flags):
        self._rbuffer.seek(0)
        lines = self.read().splitlines()
        (method, uri, version) = lines[0].split()

        self.render(method, uri)

        self._wbuffer.seek(0)
        return self._wbuffer


class CustomHTTPConnection(connbase):
    def connect(self):
        self.sock = TrackerSocket()


if __name__ == '__main__':
    conn = CustomHTTPConnection('localhost', 8000)
    conn.request('HEAD', '/v1/account/container/object')
    response = conn.getresponse()
    print "Status:", response.status, response.reason
    for (key, value) in response.getheaders():
        print "%s: %s" % (key, value)
    print response.read()
