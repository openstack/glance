# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

from glance.common import context
from glance.common import exception
from glance.registry.db import api as db_api


class RequestContext(context.RequestContext):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    Also provides tests for image visibility and sharability.
    """

    def is_image_visible(self, image):
        """Return True if the image is visible in this context."""
        # Is admin == image visible
        if self.is_admin:
            return True

        # No owner == image visible
        if image.owner is None:
            return True

        # Image is_public == image visible
        if image.is_public:
            return True

        # Perform tests based on whether we have an owner
        if self.owner is not None:
            if self.owner == image.owner:
                return True

            # Figure out if this image is shared with that tenant
            try:
                tmp = db_api.image_member_find(self, image.id, self.owner)
                return not tmp['deleted']
            except exception.NotFound:
                pass

        # Private image
        return False

    def is_image_mutable(self, image):
        """Return True if the image is mutable in this context."""
        # Is admin == image mutable
        if self.is_admin:
            return True

        # No owner == image not mutable
        if image.owner is None or self.owner is None:
            return False

        # Image only mutable by its owner
        return image.owner == self.owner

    def is_image_sharable(self, image, **kwargs):
        """Return True if the image can be shared to others in this context."""
        # Only allow sharing if we have an owner
        if self.owner is None:
            return False

        # Is admin == image sharable
        if self.is_admin:
            return True

        # If we own the image, we can share it
        if self.owner == image.owner:
            return True

        # Let's get the membership association
        if 'membership' in kwargs:
            membership = kwargs['membership']
            if membership is None:
                # Not shared with us anyway
                return False
        else:
            try:
                membership = db_api.image_member_find(self, image.id,
                                                      self.owner)
            except exception.NotFound:
                # Not shared with us anyway
                return False

        # It's the can_share attribute we're now interested in
        return membership.can_share
