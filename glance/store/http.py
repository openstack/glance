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

import glance.store


class HTTPBackend(glance.store.Backend):
    """ An implementation of the HTTP Backend Adapter """

    @classmethod
    def get(cls, parsed_uri, expected_size, options=None, conn_class=None):
        """
        Takes a parsed uri for an HTTP resource, fetches it, and
        yields the data.
        """
        if conn_class:
            pass  # use the conn_class passed in
        elif parsed_uri.scheme == "http":
            conn_class = httplib.HTTPConnection
        elif parsed_uri.scheme == "https":
            conn_class = httplib.HTTPSConnection
        else:
            raise glance.store.BackendException(
                "scheme '%s' not supported for HTTPBackend")

        conn = conn_class(parsed_uri.netloc)
        conn.request("GET", parsed_uri.path, "", {})

        try:
            return glance.store._file_iter(conn.getresponse(), cls.CHUNKSIZE)
        finally:
            conn.close()
