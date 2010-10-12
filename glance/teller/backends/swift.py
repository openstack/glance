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

from glance.teller.backends import Backend, BackendException


class SwiftBackend(Backend):
    """
    An implementation of the swift backend adapter.
    """
    EXAMPLE_URL = "swift://user:password@auth_url/container/file.gz.0"

    @classmethod
    def get(cls, parsed_uri, expected_size, conn_class=None):
        """
        Takes a parsed_uri in the format of: 
        swift://user:password@auth_url/container/file.gz.0, connects to the 
        swift instance at auth_url and downloads the file. Returns the generator
        provided by stream() on the swift object representing the file.
        """
        (user, api_key, authurl, container, file) = \
            cls.parse_swift_tokens(parsed_uri)

        if conn_class:
            pass # Use the provided conn_class
        else:
            # Import cloudfiles here because stubout will replace this call
            # with a faked swift client in the unittests, avoiding import
            # errors if the test system does not have cloudfiles installed
            import cloudfiles
            conn_class = cloudfiles

        swift_conn = conn_class.get_connection(username=user, api_key=api_key,
                                               authurl=authurl)

        container = swift_conn.get_container(container)

        obj = container.get_object(file)

        if obj.size != expected_size:
            raise BackendException("Expected %s size file, Swift has %s"
                                   % (expected_size, obj.size))

        # Return the generator provided from obj.stream()
        return obj.stream(chunksize=cls.CHUNKSIZE)

    @classmethod
    def parse_swift_tokens(cls, parsed_uri):
        """
        Parsing the swift uri is three phases:
            1) urlparse to split the tokens
            2) use RE to split on @ and /
            3) reassemble authurl
        """
        path = parsed_uri.path.lstrip('//')
        netloc = parsed_uri.netloc

        try:
            try:
                creds, netloc = netloc.split('@')
            except ValueError:
                # Python 2.6.1 compat
                # see lp659445 and Python issue7904
                creds, path = path.split('@')

            user, api_key = creds.split(':')
            path_parts = path.split('/')
            file = path_parts.pop()
            container = path_parts.pop()
        except (ValueError, IndexError):
            raise BackendException(
                 "Expected four values to unpack in: swift:%s. "
                 "Should have received something like: %s."
                 % (parsed_uri.path, cls.EXAMPLE_URL))

        authurl = "https://%s" % '/'.join(path_parts)

        return user, api_key, authurl, container, file
