# Copyright 2012 OpenStack, Foundation
# Copyright 2013 IBM Corp.
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

import copy
import functools
import uuid

from oslo_config import cfg
from oslo_log import log as logging
import six

from glance.common import exception
from glance.common import timeutils
from glance.common import utils
from glance.db import utils as db_utils
from glance.i18n import _, _LI, _LW

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

DATA = {
    'images': {},
    'members': {},
    'metadef_namespace_resource_types': [],
    'metadef_namespaces': [],
    'metadef_objects': [],
    'metadef_properties': [],
    'metadef_resource_types': [],
    'metadef_tags': [],
    'tags': {},
    'locations': [],
    'tasks': {},
    'task_info': {},
}

INDEX = 0


def log_call(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        LOG.info(_LI('Calling %(funcname)s: args=%(args)s, '
                     'kwargs=%(kwargs)s'),
                 {"funcname": func.__name__,
                  "args": args,
                  "kwargs": kwargs})
        output = func(*args, **kwargs)
        LOG.info(_LI('Returning %(funcname)s: %(output)s'),
                 {"funcname": func.__name__,
                  "output": output})
        return output
    return wrapped


def configure():
    if CONF.workers not in [0, 1]:
        msg = _('CONF.workers should be set to 0 or 1 when using the '
                'db.simple.api backend. Fore more info, see '
                'https://bugs.launchpad.net/glance/+bug/1619508')
        LOG.critical(msg)
        raise SystemExit(msg)


def reset():
    global DATA
    DATA = {
        'images': {},
        'members': [],
        'metadef_namespace_resource_types': [],
        'metadef_namespaces': [],
        'metadef_objects': [],
        'metadef_properties': [],
        'metadef_resource_types': [],
        'metadef_tags': [],
        'tags': {},
        'locations': [],
        'tasks': {},
        'task_info': {},
    }


def clear_db_env(*args, **kwargs):
    """
    Setup global environment configuration variables.

    We have no connection-oriented environment variables, so this is a NOOP.
    """
    pass


def _get_session():
    return DATA


@utils.no_4byte_params
def _image_location_format(image_id, value, meta_data, status, deleted=False):
    dt = timeutils.utcnow()
    return {
        'id': str(uuid.uuid4()),
        'image_id': image_id,
        'created_at': dt,
        'updated_at': dt,
        'deleted_at': dt if deleted else None,
        'deleted': deleted,
        'url': value,
        'metadata': meta_data,
        'status': status,
    }


def _image_property_format(image_id, name, value):
    return {
        'image_id': image_id,
        'name': name,
        'value': value,
        'deleted': False,
        'deleted_at': None,
    }


def _image_member_format(image_id, tenant_id, can_share, status='pending',
                         deleted=False):
    dt = timeutils.utcnow()
    return {
        'id': str(uuid.uuid4()),
        'image_id': image_id,
        'member': tenant_id,
        'can_share': can_share,
        'status': status,
        'created_at': dt,
        'updated_at': dt,
        'deleted': deleted,
    }


def _pop_task_info_values(values):
    task_info_values = {}
    for k, v in list(values.items()):
        if k in ['input', 'result', 'message']:
            values.pop(k)
            task_info_values[k] = v

    return task_info_values


def _format_task_from_db(task_ref, task_info_ref):
    task = copy.deepcopy(task_ref)
    if task_info_ref:
        task_info = copy.deepcopy(task_info_ref)
        task_info_values = _pop_task_info_values(task_info)
        task.update(task_info_values)
    return task


def _task_format(task_id, **values):
    dt = timeutils.utcnow()
    task = {
        'id': task_id,
        'type': 'import',
        'status': 'pending',
        'owner': None,
        'expires_at': None,
        'created_at': dt,
        'updated_at': dt,
        'deleted_at': None,
        'deleted': False,
    }
    task.update(values)
    return task


def _task_info_format(task_id, **values):
    task_info = {
        'task_id': task_id,
        'input': None,
        'result': None,
        'message': None,
    }
    task_info.update(values)
    return task_info


@utils.no_4byte_params
def _image_update(image, values, properties):
    # NOTE(bcwaldon): store properties as a list to match sqlalchemy driver
    properties = [{'name': k,
                   'value': v,
                   'image_id': image['id'],
                   'deleted': False} for k, v in properties.items()]
    if 'properties' not in image.keys():
        image['properties'] = []
    image['properties'].extend(properties)
    values = db_utils.ensure_image_dict_v2_compliant(values)
    image.update(values)
    return image


def _image_format(image_id, **values):
    dt = timeutils.utcnow()
    image = {
        'id': image_id,
        'name': None,
        'owner': None,
        'locations': [],
        'status': 'queued',
        'protected': False,
        'visibility': 'shared',
        'container_format': None,
        'disk_format': None,
        'min_ram': 0,
        'min_disk': 0,
        'size': None,
        'virtual_size': None,
        'checksum': None,
        'os_hash_algo': None,
        'os_hash_value': None,
        'tags': [],
        'created_at': dt,
        'updated_at': dt,
        'deleted_at': None,
        'deleted': False,
        'os_hidden': False
    }

    locations = values.pop('locations', None)
    if locations is not None:
        image['locations'] = []
        for location in locations:
            location_ref = _image_location_format(image_id,
                                                  location['url'],
                                                  location['metadata'],
                                                  location['status'])
            image['locations'].append(location_ref)
            DATA['locations'].append(location_ref)

    return _image_update(image, values, values.pop('properties', {}))


def _filter_images(images, filters, context,
                   status='accepted', is_public=None,
                   admin_as_user=False):
    filtered_images = []
    if 'properties' in filters:
        prop_filter = filters.pop('properties')
        filters.update(prop_filter)

    if status == 'all':
        status = None

    visibility = filters.pop('visibility', None)
    os_hidden = filters.pop('os_hidden', False)

    for image in images:
        member = image_member_find(context, image_id=image['id'],
                                   member=context.owner, status=status)
        is_member = len(member) > 0
        has_ownership = context.owner and image['owner'] == context.owner
        image_is_public = image['visibility'] == 'public'
        image_is_community = image['visibility'] == 'community'
        image_is_shared = image['visibility'] == 'shared'
        image_is_hidden = image['os_hidden'] == True
        acts_as_admin = context.is_admin and not admin_as_user
        can_see = (image_is_public
                   or image_is_community
                   or has_ownership
                   or (is_member and image_is_shared)
                   or acts_as_admin)
        if not can_see:
            continue

        if visibility:
            if visibility == 'public':
                if not image_is_public:
                    continue
            elif visibility == 'private':
                if not (image['visibility'] == 'private'):
                    continue
                if not (has_ownership or acts_as_admin):
                    continue
            elif visibility == 'shared':
                if not image_is_shared:
                    continue
            elif visibility == 'community':
                if not image_is_community:
                    continue
        else:
            if (not has_ownership) and image_is_community:
                continue

        if is_public is not None:
            if not image_is_public == is_public:
                continue

        if os_hidden:
            if image_is_hidden:
                continue

        to_add = True
        for k, value in six.iteritems(filters):
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
                to_add = image.get(key) >= value
            elif k.endswith('_max'):
                to_add = image.get(key) <= value
            elif k in ['created_at', 'updated_at']:
                attr_value = image.get(key)
                operator, isotime = utils.split_filter_op(value)
                parsed_time = timeutils.parse_isotime(isotime)
                threshold = timeutils.normalize_time(parsed_time)
                to_add = utils.evaluate_filter_op(attr_value, operator,
                                                  threshold)
            elif k in ['name', 'id', 'status',
                       'container_format', 'disk_format']:
                attr_value = image.get(key)
                operator, list_value = utils.split_filter_op(value)
                if operator == 'in':
                    threshold = utils.split_filter_value_for_quotes(list_value)
                    to_add = attr_value in threshold
                elif operator == 'eq':
                    to_add = (attr_value == list_value)
                else:
                    msg = (_("Unable to filter by unknown operator '%s'.")
                           % operator)
                    raise exception.InvalidFilterOperatorValue(msg)

            elif k != 'is_public' and image.get(k) is not None:
                to_add = image.get(key) == value
            elif k == 'tags':
                filter_tags = value
                image_tags = image_tag_get_all(context, image['id'])
                for tag in filter_tags:
                    if tag not in image_tags:
                        to_add = False
                        break
            else:
                to_add = False
                for p in image['properties']:
                    properties = {p['name']: p['value'],
                                  'deleted': p['deleted']}
                    to_add |= (properties.get(key) == value and
                               properties.get('deleted') is False)

            if not to_add:
                break

        if to_add:
            filtered_images.append(image)

    return filtered_images


def _do_pagination(context, images, marker, limit, show_deleted,
                   status='accepted'):
    start = 0
    end = -1
    if marker is None:
        start = 0
    else:
        # Check that the image is accessible
        _image_get(context, marker, force_show_deleted=show_deleted,
                   status=status)

        for i, image in enumerate(images):
            if image['id'] == marker:
                start = i + 1
                break
        else:
            raise exception.ImageNotFound()

    end = start + limit if limit is not None else None
    return images[start:end]


def _sort_images(images, sort_key, sort_dir):
    sort_key = ['created_at'] if not sort_key else sort_key

    default_sort_dir = 'desc'

    if not sort_dir:
        sort_dir = [default_sort_dir] * len(sort_key)
    elif len(sort_dir) == 1:
        default_sort_dir = sort_dir[0]
        sort_dir *= len(sort_key)

    for key in ['created_at', 'id']:
        if key not in sort_key:
            sort_key.append(key)
            sort_dir.append(default_sort_dir)

    for key in sort_key:
        if images and not (key in images[0]):
            raise exception.InvalidSortKey()

    if any(dir for dir in sort_dir if dir not in ['asc', 'desc']):
        raise exception.InvalidSortDir()

    if len(sort_key) != len(sort_dir):
        raise exception.Invalid(message='Number of sort dirs does not match '
                                        'the number of sort keys')

    for key, dir in reversed(list(zip(sort_key, sort_dir))):
        reverse = dir == 'desc'
        images.sort(key=lambda x: x[key] or '', reverse=reverse)

    return images


def image_set_property_atomic(image_id, name, value):
    try:
        image = DATA['images'][image_id]
    except KeyError:
        LOG.warn(_LW('Could not find image %s'), image_id)
        raise exception.ImageNotFound()

    prop = _image_property_format(image_id,
                                  name,
                                  value)
    image['properties'].append(prop)


def image_delete_property_atomic(image_id, name, value):
    try:
        image = DATA['images'][image_id]
    except KeyError:
        LOG.warn(_LW('Could not find image %s'), image_id)
        raise exception.ImageNotFound()

    for i, prop in enumerate(image['properties']):
        if prop['name'] == name and prop['value'] == value:
            del image['properties'][i]
            return

    raise exception.NotFound()


def _image_get(context, image_id, force_show_deleted=False, status=None):
    try:
        image = DATA['images'][image_id]
    except KeyError:
        LOG.warn(_LW('Could not find image %s'), image_id)
        raise exception.ImageNotFound()

    if image['deleted'] and not (force_show_deleted
                                 or context.can_see_deleted):
        LOG.warn(_LW('Unable to get deleted image'))
        raise exception.ImageNotFound()

    if not is_image_visible(context, image):
        LOG.warn(_LW('Unable to get unowned image'))
        raise exception.Forbidden("Image not visible to you")

    return image


@log_call
def image_get(context, image_id, session=None, force_show_deleted=False,
              v1_mode=False):
    image = copy.deepcopy(_image_get(context, image_id, force_show_deleted))
    image = _normalize_locations(context, image,
                                 force_show_deleted=force_show_deleted)
    if v1_mode:
        image = db_utils.mutate_image_dict_to_v1(image)
    return image


@log_call
def image_get_all(context, filters=None, marker=None, limit=None,
                  sort_key=None, sort_dir=None,
                  member_status='accepted', is_public=None,
                  admin_as_user=False, return_tag=False, v1_mode=False):
    filters = filters or {}
    images = DATA['images'].values()
    images = _filter_images(images, filters, context, member_status,
                            is_public, admin_as_user)
    images = _sort_images(images, sort_key, sort_dir)
    images = _do_pagination(context, images, marker, limit,
                            filters.get('deleted'))

    force_show_deleted = True if filters.get('deleted') else False
    res = []
    for image in images:
        img = _normalize_locations(context, copy.deepcopy(image),
                                   force_show_deleted=force_show_deleted)
        if return_tag:
            img['tags'] = image_tag_get_all(context, img['id'])

        if v1_mode:
            img = db_utils.mutate_image_dict_to_v1(img)
        res.append(img)
    return res


def image_restore(context, image_id):
    """Restore the pending-delete image to active."""
    image = _image_get(context, image_id)
    if image['status'] != 'pending_delete':
        msg = (_('cannot restore the image from %s to active (wanted '
                 'from_state=pending_delete)') % image['status'])
        raise exception.Conflict(msg)
    values = {'status': 'active', 'deleted': 0}
    image_update(context, image_id, values)


@log_call
def image_property_create(context, values):
    image = _image_get(context, values['image_id'])
    prop = _image_property_format(values['image_id'],
                                  values['name'],
                                  values['value'])
    image['properties'].append(prop)
    return prop


@log_call
def image_property_delete(context, prop_ref, image_ref):
    prop = None
    for p in DATA['images'][image_ref]['properties']:
        if p['name'] == prop_ref:
            prop = p
    if not prop:
        raise exception.NotFound()
    prop['deleted_at'] = timeutils.utcnow()
    prop['deleted'] = True
    return prop


@log_call
def image_member_find(context, image_id=None, member=None,
                      status=None, include_deleted=False):
    filters = []
    images = DATA['images']
    members = DATA['members']

    def is_visible(member):
        return (member['member'] == context.owner or
                images[member['image_id']]['owner'] == context.owner)

    if not context.is_admin:
        filters.append(is_visible)

    if image_id is not None:
        filters.append(lambda m: m['image_id'] == image_id)
    if member is not None:
        filters.append(lambda m: m['member'] == member)
    if status is not None:
        filters.append(lambda m: m['status'] == status)

    for f in filters:
        members = filter(f, members)
    return [copy.deepcopy(m) for m in members]


@log_call
def image_member_count(context, image_id):
    """Return the number of image members for this image

    :param image_id: identifier of image entity
    """
    if not image_id:
        msg = _("Image id is required.")
        raise exception.Invalid(msg)

    members = DATA['members']
    return len([x for x in members if x['image_id'] == image_id])


@log_call
@utils.no_4byte_params
def image_member_create(context, values):
    member = _image_member_format(values['image_id'],
                                  values['member'],
                                  values.get('can_share', False),
                                  values.get('status', 'pending'),
                                  values.get('deleted', False))
    global DATA
    DATA['members'].append(member)
    return copy.deepcopy(member)


@log_call
def image_member_update(context, member_id, values):
    global DATA
    for member in DATA['members']:
        if member['id'] == member_id:
            member.update(values)
            member['updated_at'] = timeutils.utcnow()
            return copy.deepcopy(member)
    else:
        raise exception.NotFound()


@log_call
def image_member_delete(context, member_id):
    global DATA
    for i, member in enumerate(DATA['members']):
        if member['id'] == member_id:
            del DATA['members'][i]
            break
    else:
        raise exception.NotFound()


@log_call
@utils.no_4byte_params
def image_location_add(context, image_id, location):
    deleted = location['status'] in ('deleted', 'pending_delete')
    location_ref = _image_location_format(image_id,
                                          value=location['url'],
                                          meta_data=location['metadata'],
                                          status=location['status'],
                                          deleted=deleted)
    DATA['locations'].append(location_ref)
    image = DATA['images'][image_id]
    image.setdefault('locations', []).append(location_ref)


@log_call
@utils.no_4byte_params
def image_location_update(context, image_id, location):
    loc_id = location.get('id')
    if loc_id is None:
        msg = _("The location data has an invalid ID: %d") % loc_id
        raise exception.Invalid(msg)

    deleted = location['status'] in ('deleted', 'pending_delete')
    updated_time = timeutils.utcnow()
    delete_time = updated_time if deleted else None

    updated = False
    for loc in DATA['locations']:
        if loc['id'] == loc_id and loc['image_id'] == image_id:
            loc.update({"value": location['url'],
                        "meta_data": location['metadata'],
                        "status": location['status'],
                        "deleted": deleted,
                        "updated_at": updated_time,
                        "deleted_at": delete_time})
            updated = True
            break

    if not updated:
        msg = (_("No location found with ID %(loc)s from image %(img)s") %
               dict(loc=loc_id, img=image_id))
        LOG.warn(msg)
        raise exception.NotFound(msg)


@log_call
def image_location_delete(context, image_id, location_id, status,
                          delete_time=None):
    if status not in ('deleted', 'pending_delete'):
        msg = _("The status of deleted image location can only be set to "
                "'pending_delete' or 'deleted'.")
        raise exception.Invalid(msg)

    deleted = False
    for loc in DATA['locations']:
        if loc['id'] == location_id and loc['image_id'] == image_id:
            deleted = True
            delete_time = delete_time or timeutils.utcnow()
            loc.update({"deleted": deleted,
                        "status": status,
                        "updated_at": delete_time,
                        "deleted_at": delete_time})
            break

    if not deleted:
        msg = (_("No location found with ID %(loc)s from image %(img)s") %
               dict(loc=location_id, img=image_id))
        LOG.warn(msg)
        raise exception.NotFound(msg)


def _image_locations_set(context, image_id, locations):
    # NOTE(zhiyan): 1. Remove records from DB for deleted locations
    used_loc_ids = [loc['id'] for loc in locations if loc.get('id')]
    image = DATA['images'][image_id]
    for loc in image['locations']:
        if loc['id'] not in used_loc_ids and not loc['deleted']:
            image_location_delete(context, image_id, loc['id'], 'deleted')
    for i, loc in enumerate(DATA['locations']):
        if (loc['image_id'] == image_id and loc['id'] not in used_loc_ids and
                not loc['deleted']):
            del DATA['locations'][i]

    # NOTE(zhiyan): 2. Adding or update locations
    for loc in locations:
        if loc.get('id') is None:
            image_location_add(context, image_id, loc)
        else:
            image_location_update(context, image_id, loc)


def _image_locations_delete_all(context, image_id, delete_time=None):
    image = DATA['images'][image_id]
    for loc in image['locations']:
        if not loc['deleted']:
            image_location_delete(context, image_id, loc['id'], 'deleted',
                                  delete_time=delete_time)

    for i, loc in enumerate(DATA['locations']):
        if image_id == loc['image_id'] and loc['deleted'] == False:
            del DATA['locations'][i]


def _normalize_locations(context, image, force_show_deleted=False):
    """
    Generate suitable dictionary list for locations field of image.

    We don't need to set other data fields of location record which return
    from image query.
    """

    if image['status'] == 'deactivated' and not context.is_admin:
        # Locations are not returned for a deactivated image for non-admin user
        image['locations'] = []
        return image

    if force_show_deleted:
        locations = image['locations']
    else:
        locations = [x for x in image['locations'] if not x['deleted']]
    image['locations'] = [{'id': loc['id'],
                           'url': loc['url'],
                           'metadata': loc['metadata'],
                           'status': loc['status']}
                          for loc in locations]
    return image


@log_call
def image_create(context, image_values, v1_mode=False):
    global DATA
    image_id = image_values.get('id', str(uuid.uuid4()))

    if image_id in DATA['images']:
        raise exception.Duplicate()

    if 'status' not in image_values:
        raise exception.Invalid('status is a required attribute')

    allowed_keys = set(['id', 'name', 'status', 'min_ram', 'min_disk', 'size',
                        'virtual_size', 'checksum', 'locations', 'owner',
                        'protected', 'is_public', 'container_format',
                        'disk_format', 'created_at', 'updated_at', 'deleted',
                        'deleted_at', 'properties', 'tags', 'visibility',
                        'os_hidden', 'os_hash_algo', 'os_hash_value'])

    incorrect_keys = set(image_values.keys()) - allowed_keys
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    image = _image_format(image_id, **image_values)
    DATA['images'][image_id] = image
    DATA['tags'][image_id] = image.pop('tags', [])

    image = _normalize_locations(context, copy.deepcopy(image))
    if v1_mode:
        image = db_utils.mutate_image_dict_to_v1(image)
    return image


@log_call
def image_update(context, image_id, image_values, purge_props=False,
                 from_state=None, v1_mode=False, atomic_props=None):
    global DATA
    try:
        image = DATA['images'][image_id]
    except KeyError:
        raise exception.ImageNotFound()

    location_data = image_values.pop('locations', None)
    if location_data is not None:
        _image_locations_set(context, image_id, location_data)

    if atomic_props is None:
        atomic_props = []

    # replace values for properties that already exist
    new_properties = image_values.pop('properties', {})
    for prop in image['properties']:
        if prop['name'] in atomic_props:
            continue
        elif prop['name'] in new_properties:
            prop['value'] = new_properties.pop(prop['name'])
        elif purge_props:
            # this matches weirdness in the sqlalchemy api
            prop['deleted'] = True

    image['updated_at'] = timeutils.utcnow()
    _image_update(image, image_values,
                  {k: v for k, v in new_properties.items()
                   if k not in atomic_props})
    DATA['images'][image_id] = image

    image = _normalize_locations(context, copy.deepcopy(image))
    if v1_mode:
        image = db_utils.mutate_image_dict_to_v1(image)
    return image


@log_call
def image_destroy(context, image_id):
    global DATA
    try:
        delete_time = timeutils.utcnow()
        DATA['images'][image_id]['deleted'] = True
        DATA['images'][image_id]['deleted_at'] = delete_time

        # NOTE(flaper87): Move the image to one of the deleted statuses
        # if it hasn't been done yet.
        if (DATA['images'][image_id]['status'] not in
                ['deleted', 'pending_delete']):
            DATA['images'][image_id]['status'] = 'deleted'

        _image_locations_delete_all(context, image_id,
                                    delete_time=delete_time)

        for prop in DATA['images'][image_id]['properties']:
            image_property_delete(context, prop['name'], image_id)

        members = image_member_find(context, image_id=image_id)
        for member in members:
            image_member_delete(context, member['id'])

        tags = image_tag_get_all(context, image_id)
        for tag in tags:
            image_tag_delete(context, image_id, tag)

        return _normalize_locations(context,
                                    copy.deepcopy(DATA['images'][image_id]))
    except KeyError:
        raise exception.ImageNotFound()


@log_call
def image_tag_get_all(context, image_id):
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
    DATA['tags'][image_id] = list(values)


@log_call
@utils.no_4byte_params
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


def is_image_visible(context, image, status=None):
    if status == 'all':
        status = None
    return db_utils.is_image_visible(context, image, image_member_find, status)


def user_get_storage_usage(context, owner_id, image_id=None, session=None):
    images = image_get_all(context, filters={'owner': owner_id})
    total = 0
    for image in images:
        if image['status'] in ['killed', 'deleted']:
            continue

        if image['id'] != image_id:
            locations = [loc for loc in image['locations']
                         if loc.get('status') != 'deleted']
            total += (image['size'] * len(locations))
    return total


@log_call
def task_create(context, values):
    """Create a task object"""
    global DATA

    task_values = copy.deepcopy(values)
    task_id = task_values.get('id', str(uuid.uuid4()))
    required_attributes = ['type', 'status', 'input']
    allowed_attributes = ['id', 'type', 'status', 'input', 'result', 'owner',
                          'message', 'expires_at', 'created_at',
                          'updated_at', 'deleted_at', 'deleted']

    if task_id in DATA['tasks']:
        raise exception.Duplicate()

    for key in required_attributes:
        if key not in task_values:
            raise exception.Invalid('%s is a required attribute' % key)

    incorrect_keys = set(task_values.keys()) - set(allowed_attributes)
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    task_info_values = _pop_task_info_values(task_values)
    task = _task_format(task_id, **task_values)
    DATA['tasks'][task_id] = task
    task_info = _task_info_create(task['id'], task_info_values)

    return _format_task_from_db(task, task_info)


@log_call
def task_update(context, task_id, values):
    """Update a task object"""
    global DATA
    task_values = copy.deepcopy(values)
    task_info_values = _pop_task_info_values(task_values)
    try:
        task = DATA['tasks'][task_id]
    except KeyError:
        LOG.debug("No task found with ID %s", task_id)
        raise exception.TaskNotFound(task_id=task_id)

    task.update(task_values)
    task['updated_at'] = timeutils.utcnow()
    DATA['tasks'][task_id] = task
    task_info = _task_info_update(task['id'], task_info_values)

    return _format_task_from_db(task, task_info)


@log_call
def task_get(context, task_id, force_show_deleted=False):
    task, task_info = _task_get(context, task_id, force_show_deleted)
    return _format_task_from_db(task, task_info)


def _task_get(context, task_id, force_show_deleted=False):
    try:
        task = DATA['tasks'][task_id]
    except KeyError:
        msg = _LW('Could not find task %s') % task_id
        LOG.warn(msg)
        raise exception.TaskNotFound(task_id=task_id)

    if task['deleted'] and not (force_show_deleted or context.can_see_deleted):
        msg = _LW('Unable to get deleted task %s') % task_id
        LOG.warn(msg)
        raise exception.TaskNotFound(task_id=task_id)

    if not _is_task_visible(context, task):
        LOG.debug("Forbidding request, task %s is not visible", task_id)
        msg = _("Forbidding request, task %s is not visible") % task_id
        raise exception.Forbidden(msg)

    task_info = _task_info_get(task_id)

    return task, task_info


@log_call
def task_delete(context, task_id):
    global DATA
    try:
        DATA['tasks'][task_id]['deleted'] = True
        DATA['tasks'][task_id]['deleted_at'] = timeutils.utcnow()
        DATA['tasks'][task_id]['updated_at'] = timeutils.utcnow()
        return copy.deepcopy(DATA['tasks'][task_id])
    except KeyError:
        LOG.debug("No task found with ID %s", task_id)
        raise exception.TaskNotFound(task_id=task_id)


def _task_soft_delete(context):
    """Scrub task entities which are expired """
    global DATA
    now = timeutils.utcnow()
    tasks = DATA['tasks'].values()

    for task in tasks:
        if(task['owner'] == context.owner and task['deleted'] == False
           and task['expires_at'] <= now):

            task['deleted'] = True
            task['deleted_at'] = timeutils.utcnow()


@log_call
def task_get_all(context, filters=None, marker=None, limit=None,
                 sort_key='created_at', sort_dir='desc'):
    """
    Get all tasks that match zero or more filters.

    :param filters: dict of filter keys and values.
    :param marker: task id after which to start page
    :param limit: maximum number of tasks to return
    :param sort_key: task attribute by which results should be sorted
    :param sort_dir: direction in which results should be sorted (asc, desc)
    :returns: tasks set
    """
    _task_soft_delete(context)
    filters = filters or {}
    tasks = DATA['tasks'].values()
    tasks = _filter_tasks(tasks, filters, context)
    tasks = _sort_tasks(tasks, sort_key, sort_dir)
    tasks = _paginate_tasks(context, tasks, marker, limit,
                            filters.get('deleted'))

    filtered_tasks = []
    for task in tasks:
        filtered_tasks.append(_format_task_from_db(task, task_info_ref=None))

    return filtered_tasks


def _is_task_visible(context, task):
    """Return True if the task is visible in this context."""
    # Is admin == task visible
    if context.is_admin:
        return True

    # No owner == task visible
    if task['owner'] is None:
        return True

    # Perform tests based on whether we have an owner
    if context.owner is not None:
        if context.owner == task['owner']:
            return True

    return False


def _filter_tasks(tasks, filters, context, admin_as_user=False):
    filtered_tasks = []

    for task in tasks:
        has_ownership = context.owner and task['owner'] == context.owner
        can_see = (has_ownership or (context.is_admin and not admin_as_user))
        if not can_see:
            continue

        add = True
        for k, value in six.iteritems(filters):
            add = task[k] == value and task['deleted'] is False
            if not add:
                break

        if add:
            filtered_tasks.append(task)

    return filtered_tasks


def _sort_tasks(tasks, sort_key, sort_dir):
    reverse = False
    if tasks and not (sort_key in tasks[0]):
        raise exception.InvalidSortKey()

    def keyfn(x):
        return (x[sort_key] if x[sort_key] is not None else '',
                x['created_at'], x['id'])

    reverse = sort_dir == 'desc'
    tasks.sort(key=keyfn, reverse=reverse)
    return tasks


def _paginate_tasks(context, tasks, marker, limit, show_deleted):
    start = 0
    end = -1
    if marker is None:
        start = 0
    else:
        # Check that the task is accessible
        _task_get(context, marker, force_show_deleted=show_deleted)

        for i, task in enumerate(tasks):
            if task['id'] == marker:
                start = i + 1
                break
        else:
            if task:
                raise exception.TaskNotFound(task_id=task['id'])
            else:
                msg = _("Task does not exist")
                raise exception.NotFound(message=msg)

    end = start + limit if limit is not None else None
    return tasks[start:end]


def _task_info_create(task_id, values):
    """Create a Task Info for Task with given task ID"""
    global DATA
    task_info = _task_info_format(task_id, **values)
    DATA['task_info'][task_id] = task_info

    return task_info


def _task_info_update(task_id, values):
    """Update Task Info for Task with given task ID and updated values"""
    global DATA
    try:
        task_info = DATA['task_info'][task_id]
    except KeyError:
        LOG.debug("No task info found with task id %s", task_id)
        raise exception.TaskNotFound(task_id=task_id)

    task_info.update(values)
    DATA['task_info'][task_id] = task_info

    return task_info


def _task_info_get(task_id):
    """Get Task Info for Task with given task ID"""
    global DATA
    try:
        task_info = DATA['task_info'][task_id]
    except KeyError:
        msg = _LW('Could not find task info %s') % task_id
        LOG.warn(msg)
        raise exception.TaskNotFound(task_id=task_id)

    return task_info


def _metadef_delete_namespace_content(get_func, key, context, namespace_name):
    global DATA
    metadefs = get_func(context, namespace_name)
    data = DATA[key]
    for metadef in metadefs:
        data.remove(metadef)
    return metadefs


@log_call
@utils.no_4byte_params
def metadef_namespace_create(context, values):
    """Create a namespace object"""
    global DATA

    namespace_values = copy.deepcopy(values)
    namespace_name = namespace_values.get('namespace')
    required_attributes = ['namespace', 'owner']
    allowed_attributes = ['namespace', 'owner', 'display_name', 'description',
                          'visibility', 'protected']

    for namespace in DATA['metadef_namespaces']:
        if namespace['namespace'] == namespace_name:
            LOG.debug("Can not create the metadata definition namespace. "
                      "Namespace=%s already exists.", namespace_name)
            raise exception.MetadefDuplicateNamespace(
                namespace_name=namespace_name)

    for key in required_attributes:
        if key not in namespace_values:
            raise exception.Invalid('%s is a required attribute' % key)

    incorrect_keys = set(namespace_values.keys()) - set(allowed_attributes)
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    namespace = _format_namespace(namespace_values)
    DATA['metadef_namespaces'].append(namespace)

    return namespace


@log_call
@utils.no_4byte_params
def metadef_namespace_update(context, namespace_id, values):
    """Update a namespace object"""
    global DATA
    namespace_values = copy.deepcopy(values)

    namespace = metadef_namespace_get_by_id(context, namespace_id)
    if namespace['namespace'] != values['namespace']:
        for db_namespace in DATA['metadef_namespaces']:
            if db_namespace['namespace'] == values['namespace']:
                LOG.debug("Invalid update. It would result in a duplicate "
                          "metadata definition namespace with the same "
                          "name of %s", values['namespace'])
                emsg = (_("Invalid update. It would result in a duplicate"
                          " metadata definition namespace with the same"
                          " name of %s")
                        % values['namespace'])
                raise exception.MetadefDuplicateNamespace(emsg)
    DATA['metadef_namespaces'].remove(namespace)

    namespace.update(namespace_values)
    namespace['updated_at'] = timeutils.utcnow()
    DATA['metadef_namespaces'].append(namespace)

    return namespace


@log_call
def metadef_namespace_get_by_id(context, namespace_id):
    """Get a namespace object"""
    try:
        namespace = next(namespace for namespace in DATA['metadef_namespaces']
                         if namespace['id'] == namespace_id)
    except StopIteration:
        msg = (_("Metadata definition namespace not found for id=%s")
               % namespace_id)
        LOG.warn(msg)
        raise exception.MetadefNamespaceNotFound(msg)

    if not _is_namespace_visible(context, namespace):
        LOG.debug("Forbidding request, metadata definition namespace=%s "
                  "is not visible.", namespace.namespace)
        emsg = _("Forbidding request, metadata definition namespace=%s "
                 "is not visible.") % namespace.namespace
        raise exception.MetadefForbidden(emsg)

    return namespace


@log_call
def metadef_namespace_get(context, namespace_name):
    """Get a namespace object"""
    try:
        namespace = next(namespace for namespace in DATA['metadef_namespaces']
                         if namespace['namespace'] == namespace_name)
    except StopIteration:
        LOG.debug("No namespace found with name %s", namespace_name)
        raise exception.MetadefNamespaceNotFound(
            namespace_name=namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    return namespace


@log_call
def metadef_namespace_get_all(context,
                              marker=None,
                              limit=None,
                              sort_key='created_at',
                              sort_dir='desc',
                              filters=None):
    """Get a namespaces list"""
    resource_types = filters.get('resource_types', []) if filters else []
    visibility = filters.get('visibility') if filters else None

    namespaces = []
    for namespace in DATA['metadef_namespaces']:
        if not _is_namespace_visible(context, namespace):
            continue

        if visibility and namespace['visibility'] != visibility:
            continue

        if resource_types:
            for association in DATA['metadef_namespace_resource_types']:
                if association['namespace_id'] == namespace['id']:
                    if association['name'] in resource_types:
                        break
            else:
                continue

        namespaces.append(namespace)

    return namespaces


@log_call
def metadef_namespace_delete(context, namespace_name):
    """Delete a namespace object"""
    global DATA

    namespace = metadef_namespace_get(context, namespace_name)
    DATA['metadef_namespaces'].remove(namespace)

    return namespace


@log_call
def metadef_namespace_delete_content(context, namespace_name):
    """Delete a namespace content"""
    global DATA
    namespace = metadef_namespace_get(context, namespace_name)
    namespace_id = namespace['id']

    objects = []

    for object in DATA['metadef_objects']:
        if object['namespace_id'] != namespace_id:
            objects.append(object)

    DATA['metadef_objects'] = objects

    properties = []

    for property in DATA['metadef_objects']:
        if property['namespace_id'] != namespace_id:
            properties.append(object)

    DATA['metadef_objects'] = properties

    return namespace


@log_call
def metadef_object_get(context, namespace_name, object_name):
    """Get a metadef object"""
    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    for object in DATA['metadef_objects']:
        if (object['namespace_id'] == namespace['id'] and
                object['name'] == object_name):
            return object
    else:
        LOG.debug("The metadata definition object with name=%(name)s"
                  " was not found in namespace=%(namespace_name)s.",
                  {'name': object_name, 'namespace_name': namespace_name})
        raise exception.MetadefObjectNotFound(namespace_name=namespace_name,
                                              object_name=object_name)


@log_call
def metadef_object_get_by_id(context, namespace_name, object_id):
    """Get a metadef object"""
    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    for object in DATA['metadef_objects']:
        if (object['namespace_id'] == namespace['id'] and
                object['id'] == object_id):
            return object
    else:
        msg = (_("Metadata definition object not found for id=%s")
               % object_id)
        LOG.warn(msg)
        raise exception.MetadefObjectNotFound(msg)


@log_call
def metadef_object_get_all(context, namespace_name):
    """Get a metadef objects list"""
    namespace = metadef_namespace_get(context, namespace_name)

    objects = []

    _check_namespace_visibility(context, namespace, namespace_name)

    for object in DATA['metadef_objects']:
        if object['namespace_id'] == namespace['id']:
            objects.append(object)

    return objects


@log_call
@utils.no_4byte_params
def metadef_object_create(context, namespace_name, values):
    """Create a metadef object"""
    global DATA

    object_values = copy.deepcopy(values)
    object_name = object_values['name']
    required_attributes = ['name']
    allowed_attributes = ['name', 'description', 'json_schema', 'required']

    namespace = metadef_namespace_get(context, namespace_name)

    for object in DATA['metadef_objects']:
        if (object['name'] == object_name and
                object['namespace_id'] == namespace['id']):
            LOG.debug("A metadata definition object with name=%(name)s "
                      "in namespace=%(namespace_name)s already exists.",
                      {'name': object_name, 'namespace_name': namespace_name})
            raise exception.MetadefDuplicateObject(
                object_name=object_name, namespace_name=namespace_name)

    for key in required_attributes:
        if key not in object_values:
            raise exception.Invalid('%s is a required attribute' % key)

    incorrect_keys = set(object_values.keys()) - set(allowed_attributes)
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    object_values['namespace_id'] = namespace['id']

    _check_namespace_visibility(context, namespace, namespace_name)

    object = _format_object(object_values)
    DATA['metadef_objects'].append(object)

    return object


@log_call
@utils.no_4byte_params
def metadef_object_update(context, namespace_name, object_id, values):
    """Update a metadef object"""
    global DATA

    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    object = metadef_object_get_by_id(context, namespace_name, object_id)
    if object['name'] != values['name']:
        for db_object in DATA['metadef_objects']:
            if (db_object['name'] == values['name'] and
                    db_object['namespace_id'] == namespace['id']):
                LOG.debug("Invalid update. It would result in a duplicate "
                          "metadata definition object with same name=%(name)s "
                          "in namespace=%(namespace_name)s.",
                          {'name': object['name'],
                           'namespace_name': namespace_name})
                emsg = (_("Invalid update. It would result in a duplicate"
                          " metadata definition object with the same"
                          " name=%(name)s "
                          " in namespace=%(namespace_name)s.")
                        % {'name': object['name'],
                           'namespace_name': namespace_name})
                raise exception.MetadefDuplicateObject(emsg)
    DATA['metadef_objects'].remove(object)

    object.update(values)
    object['updated_at'] = timeutils.utcnow()
    DATA['metadef_objects'].append(object)

    return object


@log_call
def metadef_object_delete(context, namespace_name, object_name):
    """Delete a metadef object"""
    global DATA

    object = metadef_object_get(context, namespace_name, object_name)
    DATA['metadef_objects'].remove(object)

    return object


def metadef_object_delete_namespace_content(context, namespace_name,
                                            session=None):
    """Delete an object or raise if namespace or object doesn't exist."""
    return _metadef_delete_namespace_content(
        metadef_object_get_all, 'metadef_objects', context, namespace_name)


@log_call
def metadef_object_count(context, namespace_name):
    """Get metadef object count in a namespace"""
    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    count = 0
    for object in DATA['metadef_objects']:
        if object['namespace_id'] == namespace['id']:
            count = count + 1

    return count


@log_call
def metadef_property_count(context, namespace_name):
    """Get properties count in a namespace"""
    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    count = 0
    for property in DATA['metadef_properties']:
        if property['namespace_id'] == namespace['id']:
            count = count + 1

    return count


@log_call
@utils.no_4byte_params
def metadef_property_create(context, namespace_name, values):
    """Create a metadef property"""
    global DATA

    property_values = copy.deepcopy(values)
    property_name = property_values['name']
    required_attributes = ['name']
    allowed_attributes = ['name', 'description', 'json_schema', 'required']

    namespace = metadef_namespace_get(context, namespace_name)

    for property in DATA['metadef_properties']:
        if (property['name'] == property_name and
                property['namespace_id'] == namespace['id']):
            LOG.debug("Can not create metadata definition property. A property"
                      " with name=%(name)s already exists in"
                      " namespace=%(namespace_name)s.",
                      {'name': property_name,
                       'namespace_name': namespace_name})
            raise exception.MetadefDuplicateProperty(
                property_name=property_name,
                namespace_name=namespace_name)

    for key in required_attributes:
        if key not in property_values:
            raise exception.Invalid('%s is a required attribute' % key)

    incorrect_keys = set(property_values.keys()) - set(allowed_attributes)
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    property_values['namespace_id'] = namespace['id']

    _check_namespace_visibility(context, namespace, namespace_name)

    property = _format_property(property_values)
    DATA['metadef_properties'].append(property)

    return property


@log_call
@utils.no_4byte_params
def metadef_property_update(context, namespace_name, property_id, values):
    """Update a metadef property"""
    global DATA

    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    property = metadef_property_get_by_id(context, namespace_name, property_id)
    if property['name'] != values['name']:
        for db_property in DATA['metadef_properties']:
            if (db_property['name'] == values['name'] and
                    db_property['namespace_id'] == namespace['id']):
                LOG.debug("Invalid update. It would result in a duplicate"
                          " metadata definition property with the same"
                          " name=%(name)s"
                          " in namespace=%(namespace_name)s.",
                          {'name': property['name'],
                           'namespace_name': namespace_name})
                emsg = (_("Invalid update. It would result in a duplicate"
                          " metadata definition property with the same"
                          " name=%(name)s"
                          " in namespace=%(namespace_name)s.")
                        % {'name': property['name'],
                           'namespace_name': namespace_name})
                raise exception.MetadefDuplicateProperty(emsg)
    DATA['metadef_properties'].remove(property)

    property.update(values)
    property['updated_at'] = timeutils.utcnow()
    DATA['metadef_properties'].append(property)

    return property


@log_call
def metadef_property_get_all(context, namespace_name):
    """Get a metadef properties list"""
    namespace = metadef_namespace_get(context, namespace_name)

    properties = []

    _check_namespace_visibility(context, namespace, namespace_name)

    for property in DATA['metadef_properties']:
        if property['namespace_id'] == namespace['id']:
            properties.append(property)

    return properties


@log_call
def metadef_property_get_by_id(context, namespace_name, property_id):
    """Get a metadef property"""
    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    for property in DATA['metadef_properties']:
        if (property['namespace_id'] == namespace['id'] and
                property['id'] == property_id):
            return property
    else:
        msg = (_("Metadata definition property not found for id=%s")
               % property_id)
        LOG.warn(msg)
        raise exception.MetadefPropertyNotFound(msg)


@log_call
def metadef_property_get(context, namespace_name, property_name):
    """Get a metadef property"""
    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    for property in DATA['metadef_properties']:
        if (property['namespace_id'] == namespace['id'] and
                property['name'] == property_name):
            return property
    else:
        LOG.debug("No property found with name=%(name)s in"
                  " namespace=%(namespace_name)s ",
                  {'name': property_name, 'namespace_name': namespace_name})
        raise exception.MetadefPropertyNotFound(namespace_name=namespace_name,
                                                property_name=property_name)


@log_call
def metadef_property_delete(context, namespace_name, property_name):
    """Delete a metadef property"""
    global DATA

    property = metadef_property_get(context, namespace_name, property_name)
    DATA['metadef_properties'].remove(property)

    return property


def metadef_property_delete_namespace_content(context, namespace_name,
                                              session=None):
    """Delete a property or raise if it or namespace doesn't exist."""
    return _metadef_delete_namespace_content(
        metadef_property_get_all, 'metadef_properties', context,
        namespace_name)


@log_call
def metadef_resource_type_create(context, values):
    """Create a metadef resource type"""
    global DATA

    resource_type_values = copy.deepcopy(values)
    resource_type_name = resource_type_values['name']

    allowed_attrubites = ['name', 'protected']

    for resource_type in DATA['metadef_resource_types']:
        if resource_type['name'] == resource_type_name:
            raise exception.Duplicate()

    incorrect_keys = set(resource_type_values.keys()) - set(allowed_attrubites)
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    resource_type = _format_resource_type(resource_type_values)
    DATA['metadef_resource_types'].append(resource_type)

    return resource_type


@log_call
def metadef_resource_type_get_all(context):
    """List all resource types"""
    return DATA['metadef_resource_types']


@log_call
def metadef_resource_type_get(context, resource_type_name):
    """Get a resource type"""
    try:
        resource_type = next(resource_type for resource_type in
                             DATA['metadef_resource_types']
                             if resource_type['name'] ==
                             resource_type_name)
    except StopIteration:
        LOG.debug("No resource type found with name %s", resource_type_name)
        raise exception.MetadefResourceTypeNotFound(
            resource_type_name=resource_type_name)

    return resource_type


@log_call
def metadef_resource_type_association_create(context, namespace_name,
                                             values):
    global DATA

    association_values = copy.deepcopy(values)

    namespace = metadef_namespace_get(context, namespace_name)
    resource_type_name = association_values['name']
    resource_type = metadef_resource_type_get(context,
                                              resource_type_name)

    required_attributes = ['name', 'properties_target', 'prefix']
    allowed_attributes = copy.deepcopy(required_attributes)

    for association in DATA['metadef_namespace_resource_types']:
        if (association['namespace_id'] == namespace['id'] and
                association['resource_type'] == resource_type['id']):
            LOG.debug("The metadata definition resource-type association of"
                      " resource_type=%(resource_type_name)s to"
                      " namespace=%(namespace_name)s, already exists.",
                      {'resource_type_name': resource_type_name,
                       'namespace_name': namespace_name})
            raise exception.MetadefDuplicateResourceTypeAssociation(
                resource_type_name=resource_type_name,
                namespace_name=namespace_name)

    for key in required_attributes:
        if key not in association_values:
            raise exception.Invalid('%s is a required attribute' % key)

    incorrect_keys = set(association_values.keys()) - set(allowed_attributes)
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    association = _format_association(namespace, resource_type,
                                      association_values)
    DATA['metadef_namespace_resource_types'].append(association)

    return association


@log_call
def metadef_resource_type_association_get(context, namespace_name,
                                          resource_type_name):
    namespace = metadef_namespace_get(context, namespace_name)
    resource_type = metadef_resource_type_get(context, resource_type_name)

    for association in DATA['metadef_namespace_resource_types']:
        if (association['namespace_id'] == namespace['id'] and
                association['resource_type'] == resource_type['id']):
            return association
    else:
        LOG.debug("No resource type association found associated with "
                  "namespace %s and resource type %s", namespace_name,
                  resource_type_name)
        raise exception.MetadefResourceTypeAssociationNotFound(
            resource_type_name=resource_type_name,
            namespace_name=namespace_name)


@log_call
def metadef_resource_type_association_get_all_by_namespace(context,
                                                           namespace_name):
    namespace = metadef_namespace_get(context, namespace_name)

    namespace_resource_types = []
    for resource_type in DATA['metadef_namespace_resource_types']:
        if resource_type['namespace_id'] == namespace['id']:
            namespace_resource_types.append(resource_type)

    return namespace_resource_types


@log_call
def metadef_resource_type_association_delete(context, namespace_name,
                                             resource_type_name):
    global DATA

    resource_type = metadef_resource_type_association_get(context,
                                                          namespace_name,
                                                          resource_type_name)
    DATA['metadef_namespace_resource_types'].remove(resource_type)

    return resource_type


@log_call
def metadef_tag_get(context, namespace_name, name):
    """Get a metadef tag"""
    namespace = metadef_namespace_get(context, namespace_name)
    _check_namespace_visibility(context, namespace, namespace_name)

    for tag in DATA['metadef_tags']:
        if tag['namespace_id'] == namespace['id'] and tag['name'] == name:
            return tag
    else:
        LOG.debug("The metadata definition tag with name=%(name)s"
                  " was not found in namespace=%(namespace_name)s.",
                  {'name': name, 'namespace_name': namespace_name})
        raise exception.MetadefTagNotFound(name=name,
                                           namespace_name=namespace_name)


@log_call
def metadef_tag_get_by_id(context, namespace_name, id):
    """Get a metadef tag"""
    namespace = metadef_namespace_get(context, namespace_name)
    _check_namespace_visibility(context, namespace, namespace_name)

    for tag in DATA['metadef_tags']:
        if tag['namespace_id'] == namespace['id'] and tag['id'] == id:
            return tag
    else:
        msg = (_("Metadata definition tag not found for id=%s") % id)
        LOG.warn(msg)
        raise exception.MetadefTagNotFound(msg)


@log_call
def metadef_tag_get_all(context, namespace_name, filters=None, marker=None,
                        limit=None, sort_key='created_at', sort_dir=None,
                        session=None):
    """Get a metadef tags list"""

    namespace = metadef_namespace_get(context, namespace_name)
    _check_namespace_visibility(context, namespace, namespace_name)

    tags = []
    for tag in DATA['metadef_tags']:
        if tag['namespace_id'] == namespace['id']:
            tags.append(tag)

    return tags


@log_call
@utils.no_4byte_params
def metadef_tag_create(context, namespace_name, values):
    """Create a metadef tag"""
    global DATA

    tag_values = copy.deepcopy(values)
    tag_name = tag_values['name']
    required_attributes = ['name']
    allowed_attributes = ['name']

    namespace = metadef_namespace_get(context, namespace_name)

    for tag in DATA['metadef_tags']:
        if tag['name'] == tag_name and tag['namespace_id'] == namespace['id']:
            LOG.debug("A metadata definition tag with name=%(name)s"
                      " in namespace=%(namespace_name)s already exists.",
                      {'name': tag_name, 'namespace_name': namespace_name})
            raise exception.MetadefDuplicateTag(
                name=tag_name, namespace_name=namespace_name)

    for key in required_attributes:
        if key not in tag_values:
            raise exception.Invalid('%s is a required attribute' % key)

    incorrect_keys = set(tag_values.keys()) - set(allowed_attributes)
    if incorrect_keys:
        raise exception.Invalid(
            'The keys %s are not valid' % str(incorrect_keys))

    tag_values['namespace_id'] = namespace['id']

    _check_namespace_visibility(context, namespace, namespace_name)

    tag = _format_tag(tag_values)
    DATA['metadef_tags'].append(tag)
    return tag


@log_call
def metadef_tag_create_tags(context, namespace_name, tag_list):
    """Create a metadef tag"""
    global DATA

    namespace = metadef_namespace_get(context, namespace_name)
    _check_namespace_visibility(context, namespace, namespace_name)

    required_attributes = ['name']
    allowed_attributes = ['name']
    data_tag_list = []
    tag_name_list = []
    for tag_value in tag_list:
        tag_values = copy.deepcopy(tag_value)
        tag_name = tag_values['name']

        for key in required_attributes:
            if key not in tag_values:
                raise exception.Invalid('%s is a required attribute' % key)

        incorrect_keys = set(tag_values.keys()) - set(allowed_attributes)
        if incorrect_keys:
            raise exception.Invalid(
                'The keys %s are not valid' % str(incorrect_keys))

        if tag_name in tag_name_list:
            LOG.debug("A metadata definition tag with name=%(name)s"
                      " in namespace=%(namespace_name)s already exists.",
                      {'name': tag_name, 'namespace_name': namespace_name})
            raise exception.MetadefDuplicateTag(
                name=tag_name, namespace_name=namespace_name)
        else:
            tag_name_list.append(tag_name)

        tag_values['namespace_id'] = namespace['id']
        data_tag_list.append(_format_tag(tag_values))

    DATA['metadef_tags'] = []
    for tag in data_tag_list:
        DATA['metadef_tags'].append(tag)

    return data_tag_list


@log_call
@utils.no_4byte_params
def metadef_tag_update(context, namespace_name, id, values):
    """Update a metadef tag"""
    global DATA

    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    tag = metadef_tag_get_by_id(context, namespace_name, id)
    if tag['name'] != values['name']:
        for db_tag in DATA['metadef_tags']:
            if (db_tag['name'] == values['name'] and
                    db_tag['namespace_id'] == namespace['id']):
                LOG.debug("Invalid update. It would result in a duplicate"
                          " metadata definition tag with same name=%(name)s "
                          " in namespace=%(namespace_name)s.",
                          {'name': tag['name'],
                           'namespace_name': namespace_name})
                raise exception.MetadefDuplicateTag(
                    name=tag['name'], namespace_name=namespace_name)

    DATA['metadef_tags'].remove(tag)

    tag.update(values)
    tag['updated_at'] = timeutils.utcnow()
    DATA['metadef_tags'].append(tag)
    return tag


@log_call
def metadef_tag_delete(context, namespace_name, name):
    """Delete a metadef tag"""
    global DATA

    tags = metadef_tag_get(context, namespace_name, name)
    DATA['metadef_tags'].remove(tags)

    return tags


def metadef_tag_delete_namespace_content(context, namespace_name,
                                         session=None):
    """Delete an tag or raise if namespace or tag doesn't exist."""
    return _metadef_delete_namespace_content(
        metadef_tag_get_all, 'metadef_tags', context, namespace_name)


@log_call
def metadef_tag_count(context, namespace_name):
    """Get metadef tag count in a namespace"""
    namespace = metadef_namespace_get(context, namespace_name)

    _check_namespace_visibility(context, namespace, namespace_name)

    count = 0
    for tag in DATA['metadef_tags']:
        if tag['namespace_id'] == namespace['id']:
            count = count + 1

    return count


def _format_association(namespace, resource_type, association_values):
    association = {
        'namespace_id': namespace['id'],
        'resource_type': resource_type['id'],
        'properties_target': None,
        'prefix': None,
        'created_at': timeutils.utcnow(),
        'updated_at': timeutils.utcnow()

    }
    association.update(association_values)
    return association


def _format_resource_type(values):
    dt = timeutils.utcnow()
    resource_type = {
        'id': _get_metadef_id(),
        'name': values['name'],
        'protected': True,
        'created_at': dt,
        'updated_at': dt
    }
    resource_type.update(values)
    return resource_type


def _format_property(values):
    property = {
        'id': _get_metadef_id(),
        'namespace_id': None,
        'name': None,
        'json_schema': None
    }
    property.update(values)
    return property


def _format_namespace(values):
    dt = timeutils.utcnow()
    namespace = {
        'id': _get_metadef_id(),
        'namespace': None,
        'display_name': None,
        'description': None,
        'visibility': 'private',
        'protected': False,
        'owner': None,
        'created_at': dt,
        'updated_at': dt
    }
    namespace.update(values)
    return namespace


def _format_object(values):
    dt = timeutils.utcnow()
    object = {
        'id': _get_metadef_id(),
        'namespace_id': None,
        'name': None,
        'description': None,
        'json_schema': None,
        'required': None,
        'created_at': dt,
        'updated_at': dt
    }
    object.update(values)
    return object


def _format_tag(values):
    dt = timeutils.utcnow()
    tag = {
        'id': _get_metadef_id(),
        'namespace_id': None,
        'name': None,
        'created_at': dt,
        'updated_at': dt
    }
    tag.update(values)
    return tag


def _is_namespace_visible(context, namespace):
    """Return true if namespace is visible in this context"""
    if context.is_admin:
        return True

    if namespace.get('visibility', '') == 'public':
        return True

    if namespace['owner'] is None:
        return True

    if context.owner is not None:
        if context.owner == namespace['owner']:
            return True

    return False


def _check_namespace_visibility(context, namespace, namespace_name):
    if not _is_namespace_visible(context, namespace):
        LOG.debug("Forbidding request, metadata definition namespace=%s "
                  "is not visible.", namespace_name)
        emsg = _("Forbidding request, metadata definition namespace=%s"
                 " is not visible.") % namespace_name
        raise exception.MetadefForbidden(emsg)


def _get_metadef_id():
    global INDEX
    INDEX += 1
    return INDEX
