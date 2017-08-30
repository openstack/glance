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

from glance.common import exception
from glance.i18n import _


def mutate_image_dict_to_v1(image):
    """
    Replaces a v2-style image dictionary's 'visibility' member with the
    equivalent v1-style 'is_public' member.
    """
    visibility = image.pop('visibility')
    is_image_public = 'public' == visibility
    image['is_public'] = is_image_public
    return image


def ensure_image_dict_v2_compliant(image):
    """
    Accepts an image dictionary that contains a v1-style 'is_public' member
    and returns the equivalent v2-style image dictionary.
    """
    if ('is_public' in image):
        if ('visibility' in image):
            msg = _("Specifying both 'visibility' and 'is_public' is not "
                    "permiitted.")
            raise exception.Invalid(msg)
        else:
            image['visibility'] = ('public' if image.pop('is_public') else
                                   'shared')
    return image


def is_image_visible(context, image, image_member_find, status=None):
    """Return True if the image is visible in this context."""
    # Is admin == image visible
    if context.is_admin:
        return True

    # No owner == image visible
    if image['owner'] is None:
        return True

    # Public or Community visibility == image visible
    if image['visibility'] in ['public', 'community']:
        return True

    # Perform tests based on whether we have an owner
    if context.owner is not None:
        if context.owner == image['owner']:
            return True

        # Figure out if this image is shared with that tenant

        if 'shared' == image['visibility']:
            members = image_member_find(context,
                                        image_id=image['id'],
                                        member=context.owner,
                                        status=status)
            if members:
                return True

    # Private image
    return False
