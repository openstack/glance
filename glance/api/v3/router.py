# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from glance.api.v3 import artifacts
from glance.common import wsgi


UUID_REGEX = (
    R'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}')


class API(wsgi.Router):

    def _get_artifacts_resource(self):
        if not self.artifacts_resource:
            self.artifacts_resource = artifacts.create_resource()
        return self.artifacts_resource

    def __init__(self, mapper):
        self.artifacts_resource = None
        artifacts_resource = self._get_artifacts_resource()
        reject_method_resource = wsgi.Resource(wsgi.RejectMethodController())

        def _check_json_content_type(environ, result):
            return "application/json" in environ["CONTENT_TYPE"]

        def _check_octet_stream_content_type(environ, result):
            return "application/octet-stream" in environ["CONTENT_TYPE"]

        def connect_routes(m, read_only):
            with m.submapper(resource_name="artifact_operations",
                             path_prefix="/{id}",
                             requirements={'id': UUID_REGEX}) as art:
                art.show()
                if not read_only:
                    art.delete()
                    art.action('update', method='PATCH')
                    art.link('publish', method='POST')

                def connect_attr_action(attr):
                    if not read_only:
                        attr.action("upload", conditions={
                            'method': ["POST", "PUT"],
                            'function': _check_octet_stream_content_type})
                        attr.action("update_property",
                                    conditions={
                                        'method': ["POST", "PUT"],
                                        'function': _check_json_content_type})
                    attr.link("download", method="GET")

                attr_map = art.submapper(resource_name="attr_operations",
                                         path_prefix="/{attr}", path_left=None)
                attr_items = art.submapper(
                    resource_name="attr_item_ops",
                    path_prefix="/{attr}/{path_left:.*}")
                connect_attr_action(attr_map)
                connect_attr_action(attr_items)

            m.connect("", action='list', conditions={'method': 'GET'},
                      state='active')
            m.connect("/drafts", action='list', conditions={'method': 'GET'},
                      state='creating')
            if not read_only:
                m.connect("/drafts", action='create',
                          conditions={'method': 'POST'})

        mapper.connect('/artifacts',
                       controller=artifacts_resource,
                       action='list_artifact_types',
                       conditions={'method': ['GET']})

        versioned = mapper.submapper(path_prefix='/artifacts/{type_name}/'
                                                 'v{type_version}',
                                     controller=artifacts_resource)

        non_versioned = mapper.submapper(path_prefix='/artifacts/{type_name}',
                                         type_version=None,
                                         controller=artifacts_resource)
        connect_routes(versioned, False)
        connect_routes(non_versioned, True)

        mapper.connect('/artifacts',
                       controller=reject_method_resource,
                       action='reject',
                       allowed_methods='GET',
                       conditions={'method': ['POST', 'PUT', 'DELETE',
                                              'PATCH', 'HEAD']})

        super(API, self).__init__(mapper)
