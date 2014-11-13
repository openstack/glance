# Copyright (c) 2014 Mirantis, Inc.
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

from glance.common.artifacts import definitions
from glance.common import exception
import glance.contrib.plugins.image_artifact.v1_1.image as v1_1

import glanceclient


from glance import i18n


_ = i18n._


class ImageAsAnArtifact(v1_1.ImageAsAnArtifact):
    __type_version__ = '2.0'

    file = definitions.BinaryObject(required=False)
    legacy_image_id = definitions.String(required=False, mutable=False,
                                         pattern=R'[0-9a-f]{8}-[0-9a-f]{4}'
                                                 R'-4[0-9a-f]{3}-[89ab]'
                                                 R'[0-9a-f]{3}-[0-9a-f]{12}')

    def __pre_publish__(self, context, *args, **kwargs):
        super(ImageAsAnArtifact, self).__pre_publish__(*args, **kwargs)
        if self.file is None and self.legacy_image_id is None:
            raise exception.InvalidArtifactPropertyValue(
                message=_("Either a file or a legacy_image_id has to be "
                          "specified")
            )
        if self.file is not None and self.legacy_image_id is not None:
            raise exception.InvalidArtifactPropertyValue(
                message=_("Both file and legacy_image_id may not be "
                          "specified at the same time"))

        if self.legacy_image_id:
            glance_endpoint = next(service['endpoints'][0]['publicURL']
                                   for service in context.service_catalog
                                   if service['name'] == 'glance')
            try:
                client = glanceclient.Client(version=2,
                                             endpoint=glance_endpoint,
                                             token=context.auth_token)
                legacy_image = client.images.get(self.legacy_image_id)
            except Exception:
                raise exception.InvalidArtifactPropertyValue(
                    message=_('Unable to get legacy image')
                )
            if legacy_image is not None:
                self.file = definitions.Blob(size=legacy_image.size,
                                             locations=[
                                                 {
                                                     "status": "active",
                                                     "value":
                                                     legacy_image.direct_url
                                                 }],
                                             checksum=legacy_image.checksum,
                                             item_key=legacy_image.id)
            else:
                raise exception.InvalidArtifactPropertyValue(
                    message=_("Legacy image was not found")
                )
