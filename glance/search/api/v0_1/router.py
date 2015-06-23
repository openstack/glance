# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

from glance.common import wsgi
from glance.search.api.v0_1 import search


class API(wsgi.Router):

    """WSGI router for Glance Catalog Search v0_1 API requests."""

    def __init__(self, mapper):

        reject_method_resource = wsgi.Resource(wsgi.RejectMethodController())

        search_catalog_resource = search.create_resource()
        mapper.connect('/search',
                       controller=search_catalog_resource,
                       action='search',
                       conditions={'method': ['GET']})
        mapper.connect('/search',
                       controller=search_catalog_resource,
                       action='search',
                       conditions={'method': ['POST']})
        mapper.connect('/search',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET, POST',
                       conditions={'method': ['PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/search/plugins',
                       controller=search_catalog_resource,
                       action='plugins_info',
                       conditions={'method': ['GET']})
        mapper.connect('/search/plugins',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        mapper.connect('/index',
                       controller=search_catalog_resource,
                       action='index',
                       conditions={'method': ['POST']})
        mapper.connect('/index',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='POST',
                       conditions={'method': ['GET', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        super(API, self).__init__(mapper)
