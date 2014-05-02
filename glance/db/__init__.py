# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2012 OpenStack Foundation
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

from oslo.config import cfg

from glance.common import crypt
from glance.common import exception
from glance.common import location_strategy
import glance.domain
import glance.domain.proxy
from glance.openstack.common import importutils


CONF = cfg.CONF
CONF.import_opt('image_size_cap', 'glance.common.config')
CONF.import_opt('metadata_encryption_key', 'glance.common.config')


def get_api():
    api = importutils.import_module(CONF.data_api)
    if hasattr(api, 'configure'):
        api.configure()
    return api


def unwrap(db_api):
    return db_api


# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])


IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'status', 'size', 'virtual_size',
                                      'disk_format', 'container_format',
                                      'min_disk', 'min_ram', 'is_public',
                                      'locations', 'checksum', 'owner',
                                      'protected'])


class ImageRepo(object):

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api

    def get(self, image_id):
        try:
            db_api_image = dict(self.db_api.image_get(self.context, image_id))
            assert not db_api_image['deleted']
        except (exception.NotFound, exception.Forbidden, AssertionError):
            msg = _("No image found with ID %s") % image_id
            raise exception.NotFound(msg)
        tags = self.db_api.image_tag_get_all(self.context, image_id)
        image = self._format_image_from_db(db_api_image, tags)
        return ImageProxy(image, self.context, self.db_api)

    def list(self, marker=None, limit=None, sort_key='created_at',
             sort_dir='desc', filters=None, member_status='accepted'):
        db_api_images = self.db_api.image_get_all(
            self.context, filters=filters, marker=marker, limit=limit,
            sort_key=sort_key, sort_dir=sort_dir,
            member_status=member_status)
        images = []
        for db_api_image in db_api_images:
            tags = self.db_api.image_tag_get_all(self.context,
                                                 db_api_image['id'])
            image = self._format_image_from_db(dict(db_api_image), tags)
            images.append(image)
        return images

    def _format_image_from_db(self, db_image, db_tags):
        visibility = 'public' if db_image['is_public'] else 'private'
        properties = {}
        for prop in db_image.pop('properties'):
            # NOTE(markwash) db api requires us to filter deleted
            if not prop['deleted']:
                properties[prop['name']] = prop['value']
        locations = db_image['locations']
        if CONF.metadata_encryption_key:
            key = CONF.metadata_encryption_key
            ld = []
            for l in locations:
                url = crypt.urlsafe_decrypt(key, l['url'])
                ld.append({'url': url, 'metadata': l['metadata']})
            locations = ld
        return glance.domain.Image(
            image_id=db_image['id'],
            name=db_image['name'],
            status=db_image['status'],
            created_at=db_image['created_at'],
            updated_at=db_image['updated_at'],
            visibility=visibility,
            min_disk=db_image['min_disk'],
            min_ram=db_image['min_ram'],
            protected=db_image['protected'],
            locations=location_strategy.get_ordered_locations(locations),
            checksum=db_image['checksum'],
            owner=db_image['owner'],
            disk_format=db_image['disk_format'],
            container_format=db_image['container_format'],
            size=db_image['size'],
            virtual_size=db_image['virtual_size'],
            extra_properties=properties,
            tags=db_tags
        )

    def _format_image_to_db(self, image):
        locations = image.locations
        if CONF.metadata_encryption_key:
            key = CONF.metadata_encryption_key
            ld = []
            for l in locations:
                url = crypt.urlsafe_encrypt(key, l['url'])
                ld.append({'url': url, 'metadata': l['metadata']})
            locations = ld
        return {
            'id': image.image_id,
            'name': image.name,
            'status': image.status,
            'created_at': image.created_at,
            'min_disk': image.min_disk,
            'min_ram': image.min_ram,
            'protected': image.protected,
            'locations': locations,
            'checksum': image.checksum,
            'owner': image.owner,
            'disk_format': image.disk_format,
            'container_format': image.container_format,
            'size': image.size,
            'virtual_size': image.virtual_size,
            'is_public': image.visibility == 'public',
            'properties': dict(image.extra_properties),
        }

    def add(self, image):
        image_values = self._format_image_to_db(image)
        if image_values['size'] > CONF.image_size_cap:
            raise exception.ImageSizeLimitExceeded
        # the updated_at value is not set in the _format_image_to_db
        # function since it is specific to image create
        image_values['updated_at'] = image.updated_at
        new_values = self.db_api.image_create(self.context, image_values)
        self.db_api.image_tag_set_all(self.context,
                                      image.image_id, image.tags)
        image.created_at = new_values['created_at']
        image.updated_at = new_values['updated_at']

    def save(self, image):
        image_values = self._format_image_to_db(image)
        if image_values['size'] > CONF.image_size_cap:
            raise exception.ImageSizeLimitExceeded
        try:
            new_values = self.db_api.image_update(self.context,
                                                  image.image_id,
                                                  image_values,
                                                  purge_props=True)
        except (exception.NotFound, exception.Forbidden):
            msg = _("No image found with ID %s") % image.image_id
            raise exception.NotFound(msg)
        self.db_api.image_tag_set_all(self.context, image.image_id,
                                      image.tags)
        image.updated_at = new_values['updated_at']

    def remove(self, image):
        image_values = self._format_image_to_db(image)
        try:
            self.db_api.image_update(self.context, image.image_id,
                                     image_values, purge_props=True)
        except (exception.NotFound, exception.Forbidden):
            msg = _("No image found with ID %s") % image.image_id
            raise exception.NotFound(msg)
        # NOTE(markwash): don't update tags?
        new_values = self.db_api.image_destroy(self.context, image.image_id)
        image.updated_at = new_values['updated_at']


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, db_api):
        self.context = context
        self.db_api = db_api
        self.image = image
        super(ImageProxy, self).__init__(image)

    def get_member_repo(self):
        member_repo = ImageMemberRepo(self.context, self.db_api,
                                      self.image)
        return member_repo


class ImageMemberRepo(object):

    def __init__(self, context, db_api, image):
        self.context = context
        self.db_api = db_api
        self.image = image

    def _format_image_member_from_db(self, db_image_member):
        return glance.domain.ImageMembership(
            id=db_image_member['id'],
            image_id=db_image_member['image_id'],
            member_id=db_image_member['member'],
            status=db_image_member['status'],
            created_at=db_image_member['created_at'],
            updated_at=db_image_member['updated_at']
        )

    def _format_image_member_to_db(self, image_member):
        image_member = {'image_id': self.image.image_id,
                        'member': image_member.member_id,
                        'status': image_member.status,
                        'created_at': image_member.created_at}
        return image_member

    def list(self):
        db_members = self.db_api.image_member_find(
            self.context, image_id=self.image.image_id)
        image_members = []
        for db_member in db_members:
            image_members.append(self._format_image_member_from_db(db_member))
        return image_members

    def add(self, image_member):
        try:
            self.get(image_member.member_id)
        except exception.NotFound:
            pass
        else:
            msg = _('The target member %(member_id)s is already '
                    'associated with image %(image_id)s.') % {
                        'member_id': image_member.member_id,
                        'image_id': self.image.image_id}
            raise exception.Duplicate(msg)

        image_member_values = self._format_image_member_to_db(image_member)
        new_values = self.db_api.image_member_create(self.context,
                                                     image_member_values)
        image_member.created_at = new_values['created_at']
        image_member.updated_at = new_values['updated_at']
        image_member.id = new_values['id']

    def remove(self, image_member):
        try:
            self.db_api.image_member_delete(self.context, image_member.id)
        except (exception.NotFound, exception.Forbidden):
            msg = _("The specified member %s could not be found")
            raise exception.NotFound(msg % image_member.id)

    def save(self, image_member):
        image_member_values = self._format_image_member_to_db(image_member)
        try:
            new_values = self.db_api.image_member_update(self.context,
                                                         image_member.id,
                                                         image_member_values)
        except (exception.NotFound, exception.Forbidden):
            raise exception.NotFound()
        image_member.updated_at = new_values['updated_at']

    def get(self, member_id):
        try:
            db_api_image_member = self.db_api.image_member_find(
                self.context,
                self.image.image_id,
                member_id)
            if not db_api_image_member:
                raise exception.NotFound()
        except (exception.NotFound, exception.Forbidden):
            raise exception.NotFound()

        image_member = self._format_image_member_from_db(
            db_api_image_member[0])
        return image_member


class TaskRepo(object):

    def _format_task_from_db(self, db_task):
        return glance.domain.Task(
            task_id=db_task['id'],
            task_type=db_task['type'],
            status=db_task['status'],
            owner=db_task['owner'],
            expires_at=db_task['expires_at'],
            created_at=db_task['created_at'],
            updated_at=db_task['updated_at'],
        )

    def _format_task_details_from_db(self, db_task):
        return glance.domain.TaskDetails(
            task_id=db_task['id'],
            task_input=db_task['input'],
            result=db_task['result'],
            message=db_task['message'],
        )

    def _format_task_to_db(self, task, task_details=None):
        task = {'id': task.task_id,
                'type': task.type,
                'status': task.status,
                'input': None,
                'result': None,
                'owner': task.owner,
                'message': None,
                'expires_at': task.expires_at,
                'created_at': task.created_at,
                'updated_at': task.updated_at}

        if task_details is not None:
            task.update({
                'input': task_details.input,
                'result': task_details.result,
                'message': task_details.message,
            })

        return task

    def __init__(self, context, db_api):
        self.context = context
        self.db_api = db_api

    def get_task_and_details(self, task_id):
        try:
            db_api_task = self.db_api.task_get(self.context, task_id)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find task %s') % task_id
            raise exception.NotFound(msg)
        return (self._format_task_from_db(db_api_task),
                self._format_task_details_from_db(db_api_task))

    def list_tasks(self,
                   marker=None,
                   limit=None,
                   sort_key='created_at',
                   sort_dir='desc',
                   filters=None):
        db_api_tasks = self.db_api.task_get_all(self.context,
                                                filters=filters,
                                                marker=marker,
                                                limit=limit,
                                                sort_key=sort_key,
                                                sort_dir=sort_dir)
        return [self._format_task_from_db(task) for task in db_api_tasks]

    def save(self, task, task_details=None):
        task_values = self._format_task_to_db(task, task_details)
        try:
            updated_values = self.db_api.task_update(self.context,
                                                     task.task_id,
                                                     task_values)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find task %s') % task.task_id
            raise exception.NotFound(msg)
        task.updated_at = updated_values['updated_at']

    def add(self, task, task_details=None):
        task_values = self._format_task_to_db(task, task_details)
        updated_values = self.db_api.task_create(self.context, task_values)
        task.created_at = updated_values['created_at']
        task.updated_at = updated_values['updated_at']

    def remove(self, task):
        task_values = self._format_task_to_db(task)
        try:
            self.db_api.task_update(self.context, task.task_id, task_values)
            updated_values = self.db_api.task_delete(self.context,
                                                     task.task_id)
        except (exception.NotFound, exception.Forbidden):
            msg = _('Could not find task %s') % task.task_id
            raise exception.NotFound(msg)
        task.updated_at = updated_values['updated_at']
        task.deleted_at = updated_values['deleted_at']
