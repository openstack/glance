# Copyright 2012 OpenStack, LLC
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

import datetime
import functools
import uuid

from glance.common import exception
import glance.openstack.common.log as logging
from glance.openstack.common import timeutils


LOG = logging.getLogger(__name__)

DATA = {
    'images': {},
    'members': {},
    'tags': {},
}


def log_call(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        LOG.info('Calling %s: args=%s, kwargs=%s' %
                 (func.__name__, args, kwargs))
        output = func(*args, **kwargs)
        LOG.info('Returning %s: %s' % (func.__name__, output))
        return output
    return wrapped


def reset():
    global DATA
    DATA = {
        'images': {},
        'members': [],
        'tags': {},
    }


def configure_db(*args, **kwargs):
    pass


def get_session():
    return DATA


def _image_property_format(image_id, name, value):
    return {
        'image_id': image_id,
        'name': name,
        'value': value,
        'deleted': False,
        'deleted_at': None,
    }


def _image_member_format(image_id, tenant_id, can_share):
    return {
        'image_id': image_id,
        'member': tenant_id,
        'can_share': can_share,
        'deleted': False,
        'deleted_at': None,
    }


def _image_format(image_id, **values):
    dt = datetime.datetime.now()
    image = {
        'id': image_id,
        'name': None,
        'owner': None,
        'location': None,
        'status': 'queued',
        'protected': False,
        'is_public': False,
        'container_format': None,
        'disk_format': None,
        'min_ram': 0,
        'min_disk': 0,
        'size': None,
        'checksum': None,
        'tags': [],
        'created_at': dt,
        'updated_at': dt,
        'deleted_at': None,
        'deleted': False,
    }

    #NOTE(bcwaldon): store properties as a list to match sqlalchemy driver
    properties = values.pop('properties', {})
    properties = [{'name': k,
                   'value': v,
                   'deleted': False} for k, v in properties.items()]
    image['properties'] = properties

    image.update(values)
    return image


def _filter_images(images, filters, context):
    filtered_images = []
    if 'properties' in filters:
        prop_filter = filters.pop('properties')
        filters.update(prop_filter)

    is_public_filter = filters.pop('is_public', None)

    for i, image in enumerate(images):
        add = True
        for k, value in filters.iteritems():
            key = k
            if k.endswith('_min') or k.endswith('_max'):
                key = key[0:-4]
                try:
                    value = int(value)
                except ValueError:
                    msg = _("Unable to filter on a range "
                            "with a non-numeric value.")
                    raise exception.InvalidFilterRangeValue(msg)
            if k.endswith('_min'):
                add = image.get(key) >= value
            elif k.endswith('_max'):
                add = image.get(key) <= value
            elif image.get(k) is not None:
                add = image.get(key) == value
            else:
                properties = {}
                for p in image['properties']:
                    properties = {p['name']: p['value'],
                                  'deleted': p['deleted']}
                add = properties.get(key) == value and \
                                             properties.get('deleted') is False
            if not add:
                break

        if add:
            filtered_images.append(image)

    #NOTE(bcwaldon): This hacky code is only here to match what the
    # sqlalchemy driver wants - refactor it out of the db layer when
    # it seems appropriate
    if is_public_filter is not None:
        def _filter_ownership(image):
            has_ownership = image['owner'] == context.owner
            can_see = image['is_public'] or has_ownership or context.is_admin

            if can_see:
                return has_ownership or \
                        (can_see and image['is_public'] == is_public_filter)
            else:
                return False

        filtered_images = filter(_filter_ownership, filtered_images)

    return filtered_images


def _do_pagination(context, images, marker, limit, show_deleted):
    start = 0
    end = -1
    if marker is None:
        start = 0
    else:
        # Check that the image is accessible
        image_get(context, marker, force_show_deleted=show_deleted)

        for i, image in enumerate(images):
            if image['id'] == marker:
                start = i + 1
                break
        else:
            raise exception.NotFound()

    end = start + limit if limit is not None else None
    return images[start:end]


def _sort_images(images, sort_key, sort_dir):
    reverse = False
    if images and not images[0].get(sort_key):
        raise exception.InvalidSortKey()
    keyfn = lambda x: (x[sort_key], x['created_at'], x['id'])
    reverse = sort_dir == 'desc'
    images.sort(key=keyfn, reverse=reverse)

    return images


@log_call
def image_get(context, image_id, session=None, force_show_deleted=False):
    try:
        image = DATA['images'][image_id]
    except KeyError:
        LOG.info('Could not find image %s' % image_id)
        raise exception.NotFound()

    if image['deleted'] and not (force_show_deleted or context.show_deleted):
        LOG.info('Unable to get deleted image')
        raise exception.NotFound()

    if (not context.is_admin) \
            and (not image.get('is_public')) \
            and (image['owner'] is not None) \
            and (image['owner'] != context.owner):
        LOG.info('Unable to get unowned image')
        raise exception.Forbidden()

    return image


@log_call
def image_get_all(context, filters=None, marker=None, limit=None,
                  sort_key='created_at', sort_dir='desc'):
    filters = filters or {}
    images = DATA['images'].values()
    images = _filter_images(images, filters, context)
    images = _sort_images(images, sort_key, sort_dir)
    images = _do_pagination(context, images, marker, limit,
                            filters.get('deleted'))
    return images


@log_call
def image_property_create(context, values):
    image = image_get(context, values['image_id'])
    prop = _image_property_format(values['image_id'], values['name'],
                values['value'])
    image['properties'].append(prop)
    return prop


@log_call
def image_property_delete(context, prop_ref, session=None):
    image_id = prop_ref['image_id']
    prop = None
    for p in DATA['images'][image_id]['properties']:
        if p['name'] == prop_ref['name']:
            prop = p
    if not prop:
        raise exception.NotFound()
    prop['deleted_at'] = datetime.datetime.utcnow()
    prop['deleted'] = True
    return prop


@log_call
def image_member_find(context, image_id=None, member=None):
    filters = []
    if image_id is not None:
        filters.append(lambda m: m['image_id'] == image_id)
    if member is not None:
        filters.append(lambda m: m['member'] == member)

    members = DATA['members']
    for f in filters:
        members = filter(f, members)
    return members


@log_call
def image_member_create(context, values):
    member = _image_member_format(values['image_id'],
                                  values['member'],
                                  values.get('can_share', False))
    global DATA
    DATA['members'].append(member)
    return member


@log_call
def image_member_delete(context, member):
    global DATA
    mem = None
    for p in DATA['members']:
        if (p['member'] == member['member'] and
            p['image_id'] == member['image_id']):
            mem = p
    if not mem:
        raise exception.NotFound()
    mem['deleted_at'] = datetime.datetime.utcnow()
    mem['deleted'] = True
    return mem


@log_call
def image_create(context, image_values):
    global DATA
    image_id = image_values.get('id', str(uuid.uuid4()))

    if image_id in DATA['images']:
        raise exception.Duplicate()

    if 'status' not in image_values:
        raise exception.Invalid('status is a required attribute')

    allowed_keys = set(['id', 'name', 'status', 'min_ram', 'min_disk', 'size',
                        'checksum', 'location', 'owner', 'protected',
                        'is_public', 'container_format', 'disk_format',
                        'created_at', 'updated_at', 'deleted_at', 'deleted',
                        'properties', 'tags'])

    if set(image_values.keys()) - allowed_keys:
        raise exception.Invalid()

    image = _image_format(image_id, **image_values)
    DATA['images'][image_id] = image
    DATA['tags'][image_id] = image.pop('tags', [])
    return image


@log_call
def image_update(context, image_id, image_values, purge_props=False):
    global DATA
    try:
        image = DATA['images'][image_id]
    except KeyError:
        raise exception.NotFound(image_id=image_id)

    # replace values for properties that already exist
    new_properties = image_values.pop('properties', {})
    for prop in image['properties']:
        if prop['name'] in new_properties:
            prop['value'] = new_properties.pop(prop['name'])
        elif purge_props:
            # this matches weirdness in the sqlalchemy api
            prop['deleted'] = True

    # add in any completly new properties
    image['properties'].extend([
            {'name': k, 'value': v, 'deleted': False}
             for k, v in new_properties.items()])

    image['updated_at'] = timeutils.utcnow()
    image.update(image_values)
    DATA['images'][image_id] = image
    return image


@log_call
def image_destroy(context, image_id):
    global DATA
    try:
        DATA['images'][image_id]['deleted'] = True
        DATA['images'][image_id]['deleted_at'] = datetime.datetime.utcnow()
    except KeyError:
        raise exception.NotFound()


@log_call
def image_tag_get_all(context, image_id):
    image_get(context, image_id)
    return DATA['tags'].get(image_id, [])


@log_call
def image_tag_get(context, image_id, value):
    tags = image_tag_get_all(context, image_id)
    if value in tags:
        return value
    else:
        raise exception.NotFound()


@log_call
def image_tag_set_all(context, image_id, values):
    global DATA
    DATA['tags'][image_id] = values


@log_call
def image_tag_create(context, image_id, value):
    global DATA
    DATA['tags'][image_id].append(value)
    return value


@log_call
def image_tag_delete(context, image_id, value):
    global DATA
    try:
        DATA['tags'][image_id].remove(value)
    except ValueError:
        raise exception.NotFound()


def is_image_mutable(context, image):
    """Return True if the image is mutable in this context."""
    # Is admin == image mutable
    if context.is_admin:
        return True

    # No owner == image not mutable
    if image['owner'] is None or context.owner is None:
        return False

    # Image only mutable by its owner
    return image['owner'] == context.owner


def is_image_sharable(context, image, **kwargs):
    """Return True if the image can be shared to others in this context."""
    # Is admin == image sharable
    if context.is_admin:
        return True

    # Only allow sharing if we have an owner
    if context.owner is None:
        return False

    # If we own the image, we can share it
    if context.owner == image['owner']:
        return True

    # Let's get the membership association
    if 'membership' in kwargs:
        member = kwargs['membership']
        if member is None:
            # Not shared with us anyway
            return False
    else:
        members = image_member_find(context,
                                    image_id=image['id'],
                                    member=context.owner)
        if members:
            member = members[0]
        else:
            # Not shared with us anyway
            return False

    # It's the can_share attribute we're now interested in
    return member['can_share']


def is_image_visible(context, image):
    """Return True if the image is visible in this context."""
    # Is admin == image visible
    if context.is_admin:
        return True

    # No owner == image visible
    if image['owner'] is None:
        return True

    # Image is_public == image visible
    if image['is_public']:
        return True

    # Perform tests based on whether we have an owner
    if context.owner is not None:
        if context.owner == image['owner']:
            return True

        # Figure out if this image is shared with that tenant
        members = image_member_find(context,
                                    image_id=image['id'],
                                    member=context.owner)
        if members:
            return not members[0]['deleted']

    # Private image
    return False
