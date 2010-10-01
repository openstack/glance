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

import httplib
import json
import urlparse

class ParallaxAdapterException(Exception):
    pass

class ParallaxAdapter(object):
    """
    ParallaxAdapter stuff
    """

    @classmethod
    def lookup(cls, image_uri):
        """
        Take an image uri from Nova, and check if that parallax instance has a
        register of it. Takes an unparsed URI, returns a dict of the image 
        registration metadata or None.
        """

        parsed_image_uri = urlparse.urlparse(image_uri)
        if parsed_image_uri.scheme == 'http':
            conn_class = httplib.HTTPConnection
        elif parsed_image_uri.scheme == 'https':
            conn_class = httplib.HTTPSConnection

        try:
            conn = conn_class(parsed_image_uri.netloc)
            conn.request('GET', parsed_image_uri.path, "", {})
            response = conn.getresponse()

            # The image exists
            if response.status == 200: 
                result = response.read()
                
                json = json.loads(result)
                
                try:
                    return json["image"]
                except KeyError:
                    raise ParallaxAdapterException("Missing 'image' key")

        finally:
            conn.close()


class FakeParallaxAdapter(ParallaxAdapter):
    """
    A Mock ParallaxAdapter returns a mocked response for any uri with 
    one or more 'success' and None for everything else.
    """
    @classmethod
    def lookup(cls, image_uri):
        if image_uri.count("success"):
            # A successful attempt
            mock_res = {"files": [{"location":"teststr://chunk0", "size":1235},
                                  {"location": "teststr://chunk1", "size":12345}]}
            return mock_res


