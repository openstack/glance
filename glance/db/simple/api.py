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
import logging
import uuid

from glance.common import exception


LOG = logging.getLogger(__name__)

DATA = {
    'images': {},
    'members': {},
    'tags': {},
}


def configure_db(*args, **kwargs):
    pass


def get_session():
    return DATA


def _image_member_format(image_id, tenant_id, can_share):
    return {
        'image_id': image_id,
        'member': tenant_id,
        'can_share': can_share,
        'deleted': False,
    }


def _image_format(image_id, **values):
    dt = datetime.datetime.now()
    image = {
        'id': image_id,
        'name': 'image-name',
        'owner': None,
        'location': None,
        'status': 'queued',
        'is_public': False,
        'created_at': dt,
        'updated_at': dt,
        'tags': [],
        'properties': [],
    }
    image.update(values)
    return image


def image_get(context, image_id, session=None):
    try:
        image = DATA['images'][image_id]
        LOG.info('Found image %s: %s' % (image_id, str(image)))
    except KeyError:
        LOG.info('Could not find image %s' % image_id)
        raise exception.NotFound(image_id=image_id)

    #NOTE(bcwaldon: this is a hack until we can get image members with
    # a direct db call
    image['members'] = DATA['members'].get(image_id, [])

    return image


def image_get_all(context, filters=None):
    images = DATA['images'].values()
    LOG.info('Listing images: %s' % (images))
    return images


def image_member_find(context, image_id, tenant_id):
    image_get(context, image_id)

    print DATA['members']
    for member in DATA['members'].get(image_id, []):
        if member['member'] == tenant_id:
            return member

    raise exception.NotFound()


def image_member_create(context, values):
    member = _image_member_format(values['image_id'],
                                  values['member'],
                                  values['can_share'])
    global DATA
    DATA['members'].setdefault(values['image_id'], [])
    DATA['members'][values['image_id']].append(member)
    return member


def image_create(context, image_values):
    image_id = image_values.get('id', str(uuid.uuid4()))
    image = _image_format(image_id, **image_values)
    DATA['images'][image_id] = image
    DATA['tags'][image_id] = image.pop('tags', [])
    LOG.info('Created image %s with values %s' %
             (image_id, str(image_values)))
    return image


def image_update(context, image_id, image_values):
    LOG.info('Updating image %s with values %s' %
             (image_id, str(image_values)))
    global DATA
    try:
        image = DATA['images'][image_id]
        LOG.info('Found image %s: %s' % (image_id, str(image)))
    except KeyError:
        raise exception.NotFound(image_id=image_id)

    image.update(image_values)
    DATA['images'][image_id] = image
    LOG.info('Image %s updated to %s' % (image_id, str(image)))
    return image


def image_tag_get_all(context, image_id):
    image_get(context, image_id)
    return DATA['tags'].get(image_id, [])


def image_tag_get(context, image_id, value):
    tags = image_tag_get_all(context, image_id)
    if value in tags:
        return value
    else:
        raise exception.NotFound()


def image_tag_set_all(context, image_id, values):
    global DATA
    DATA['tags'][image_id] = values


def image_tag_create(context, image_id, value):
    global DATA
    DATA['tags'][image_id].append(value)
    return value


def image_tag_delete(context, image_id, value):
    global DATA
    try:
        DATA['tags'][image_id].remove(value)
    except ValueError:
        raise exception.NotFound()
