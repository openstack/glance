# Copyright 2013 OpenStack Foundation
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


def _proxy(target, attr):
    def get_attr(self):
        return getattr(getattr(self, target), attr)

    def set_attr(self, value):
        return setattr(getattr(self, target), attr, value)

    def del_attr(self):
        return delattr(getattr(self, target), attr)

    return property(get_attr, set_attr, del_attr)


class Helper(object):
    def __init__(self, proxy_class=None, proxy_kwargs=None):
        self.proxy_class = proxy_class
        self.proxy_kwargs = proxy_kwargs or {}

    def proxy(self, obj):
        if obj is None or self.proxy_class is None:
            return obj
        return self.proxy_class(obj, **self.proxy_kwargs)

    def unproxy(self, obj):
        if obj is None or self.proxy_class is None:
            return obj
        return obj.base


class TaskRepo(object):
    def __init__(self, base,
                 task_proxy_class=None, task_proxy_kwargs=None):
        self.base = base
        self.task_proxy_helper = Helper(task_proxy_class, task_proxy_kwargs)

    def get(self, task_id):
        task = self.base.get(task_id)
        return self.task_proxy_helper.proxy(task)

    def add(self, task):
        self.base.add(self.task_proxy_helper.unproxy(task))

    def save(self, task):
        self.base.save(self.task_proxy_helper.unproxy(task))

    def remove(self, task):
        base_task = self.task_proxy_helper.unproxy(task)
        self.base.remove(base_task)


class TaskStubRepo(object):
    def __init__(self, base, task_stub_proxy_class=None,
                 task_stub_proxy_kwargs=None):
        self.base = base
        self.task_stub_proxy_helper = Helper(task_stub_proxy_class,
                                             task_stub_proxy_kwargs)

    def list(self, *args, **kwargs):
        tasks = self.base.list(*args, **kwargs)
        return [self.task_stub_proxy_helper.proxy(task) for task in tasks]


class Repo(object):
    def __init__(self, base, item_proxy_class=None, item_proxy_kwargs=None):
        self.base = base
        self.helper = Helper(item_proxy_class, item_proxy_kwargs)

    def get(self, item_id):
        return self.helper.proxy(self.base.get(item_id))

    def list(self, *args, **kwargs):
        items = self.base.list(*args, **kwargs)
        return [self.helper.proxy(item) for item in items]

    def add(self, item):
        base_item = self.helper.unproxy(item)
        result = self.base.add(base_item)
        return self.helper.proxy(result)

    def save(self, item, from_state=None):
        base_item = self.helper.unproxy(item)
        result = self.base.save(base_item, from_state=from_state)
        return self.helper.proxy(result)

    def remove(self, item):
        base_item = self.helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.helper.proxy(result)

    def set_property_atomic(self, item, name, value):
        msg = '%s is only valid for images' % __name__
        assert hasattr(item, 'image_id'), msg
        self.base.set_property_atomic(item, name, value)

    def delete_property_atomic(self, item, name, value):
        msg = '%s is only valid for images' % __name__
        assert hasattr(item, 'image_id'), msg
        self.base.delete_property_atomic(item, name, value)


class MemberRepo(object):
    def __init__(self, image, base,
                 member_proxy_class=None, member_proxy_kwargs=None):
        self.image = image
        self.base = base
        self.member_proxy_helper = Helper(member_proxy_class,
                                          member_proxy_kwargs)

    def get(self, member_id):
        member = self.base.get(member_id)
        return self.member_proxy_helper.proxy(member)

    def add(self, member):
        self.base.add(self.member_proxy_helper.unproxy(member))

    def list(self, *args, **kwargs):
        members = self.base.list(*args, **kwargs)
        return [self.member_proxy_helper.proxy(member) for member
                in members]

    def remove(self, member):
        base_item = self.member_proxy_helper.unproxy(member)
        result = self.base.remove(base_item)
        return self.member_proxy_helper.proxy(result)

    def save(self, member, from_state=None):
        base_item = self.member_proxy_helper.unproxy(member)
        result = self.base.save(base_item, from_state=from_state)
        return self.member_proxy_helper.proxy(result)


class ImageFactory(object):
    def __init__(self, base, proxy_class=None, proxy_kwargs=None):
        self.helper = Helper(proxy_class, proxy_kwargs)
        self.base = base

    def new_image(self, **kwargs):
        return self.helper.proxy(self.base.new_image(**kwargs))


class ImageMembershipFactory(object):
    def __init__(self, base, proxy_class=None, proxy_kwargs=None):
        self.helper = Helper(proxy_class, proxy_kwargs)
        self.base = base

    def new_image_member(self, image, member, **kwargs):
        return self.helper.proxy(self.base.new_image_member(image,
                                                            member,
                                                            **kwargs))


class Image(object):
    def __init__(self, base, member_repo_proxy_class=None,
                 member_repo_proxy_kwargs=None):
        self.base = base
        self.helper = Helper(member_repo_proxy_class,
                             member_repo_proxy_kwargs)

    name = _proxy('base', 'name')
    image_id = _proxy('base', 'image_id')
    status = _proxy('base', 'status')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')
    visibility = _proxy('base', 'visibility')
    min_disk = _proxy('base', 'min_disk')
    min_ram = _proxy('base', 'min_ram')
    protected = _proxy('base', 'protected')
    os_hidden = _proxy('base', 'os_hidden')
    locations = _proxy('base', 'locations')
    checksum = _proxy('base', 'checksum')
    os_hash_algo = _proxy('base', 'os_hash_algo')
    os_hash_value = _proxy('base', 'os_hash_value')
    owner = _proxy('base', 'owner')
    disk_format = _proxy('base', 'disk_format')
    container_format = _proxy('base', 'container_format')
    size = _proxy('base', 'size')
    virtual_size = _proxy('base', 'virtual_size')
    extra_properties = _proxy('base', 'extra_properties')
    tags = _proxy('base', 'tags')

    def delete(self):
        self.base.delete()

    def deactivate(self):
        self.base.deactivate()

    def reactivate(self):
        self.base.reactivate()

    def set_data(self, data, size=None, backend=None, set_active=True):
        self.base.set_data(data, size, backend=backend, set_active=set_active)

    def get_data(self, *args, **kwargs):
        return self.base.get_data(*args, **kwargs)


class ImageMember(object):
    def __init__(self, base):
        self.base = base

    id = _proxy('base', 'id')
    image_id = _proxy('base', 'image_id')
    member_id = _proxy('base', 'member_id')
    status = _proxy('base', 'status')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')


class Task(object):
    def __init__(self, base):
        self.base = base

    task_id = _proxy('base', 'task_id')
    type = _proxy('base', 'type')
    status = _proxy('base', 'status')
    owner = _proxy('base', 'owner')
    expires_at = _proxy('base', 'expires_at')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')
    task_input = _proxy('base', 'task_input')
    result = _proxy('base', 'result')
    message = _proxy('base', 'message')

    def begin_processing(self):
        self.base.begin_processing()

    def succeed(self, result):
        self.base.succeed(result)

    def fail(self, message):
        self.base.fail(message)

    def run(self, executor):
        self.base.run(executor)


class TaskStub(object):
    def __init__(self, base):
        self.base = base

    task_id = _proxy('base', 'task_id')
    type = _proxy('base', 'type')
    status = _proxy('base', 'status')
    owner = _proxy('base', 'owner')
    expires_at = _proxy('base', 'expires_at')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')


class TaskFactory(object):
    def __init__(self,
                 base,
                 task_proxy_class=None,
                 task_proxy_kwargs=None):
        self.task_helper = Helper(task_proxy_class, task_proxy_kwargs)
        self.base = base

    def new_task(self, **kwargs):
        t = self.base.new_task(**kwargs)
        return self.task_helper.proxy(t)


# Metadef Namespace classes
class MetadefNamespaceRepo(object):
    def __init__(self, base,
                 namespace_proxy_class=None, namespace_proxy_kwargs=None):
        self.base = base
        self.namespace_proxy_helper = Helper(namespace_proxy_class,
                                             namespace_proxy_kwargs)

    def get(self, namespace):
        namespace_obj = self.base.get(namespace)
        return self.namespace_proxy_helper.proxy(namespace_obj)

    def add(self, namespace):
        self.base.add(self.namespace_proxy_helper.unproxy(namespace))

    def list(self, *args, **kwargs):
        namespaces = self.base.list(*args, **kwargs)
        return [self.namespace_proxy_helper.proxy(namespace) for namespace
                in namespaces]

    def remove(self, item):
        base_item = self.namespace_proxy_helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.namespace_proxy_helper.proxy(result)

    def remove_objects(self, item):
        base_item = self.namespace_proxy_helper.unproxy(item)
        result = self.base.remove_objects(base_item)
        return self.namespace_proxy_helper.proxy(result)

    def remove_properties(self, item):
        base_item = self.namespace_proxy_helper.unproxy(item)
        result = self.base.remove_properties(base_item)
        return self.namespace_proxy_helper.proxy(result)

    def remove_tags(self, item):
        base_item = self.namespace_proxy_helper.unproxy(item)
        result = self.base.remove_tags(base_item)
        return self.namespace_proxy_helper.proxy(result)

    def save(self, item):
        base_item = self.namespace_proxy_helper.unproxy(item)
        result = self.base.save(base_item)
        return self.namespace_proxy_helper.proxy(result)


class MetadefNamespace(object):
    def __init__(self, base):
        self.base = base

    namespace_id = _proxy('base', 'namespace_id')
    namespace = _proxy('base', 'namespace')
    display_name = _proxy('base', 'display_name')
    description = _proxy('base', 'description')
    owner = _proxy('base', 'owner')
    visibility = _proxy('base', 'visibility')
    protected = _proxy('base', 'protected')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')

    def delete(self):
        self.base.delete()


class MetadefNamespaceFactory(object):
    def __init__(self,
                 base,
                 meta_namespace_proxy_class=None,
                 meta_namespace_proxy_kwargs=None):
        self.meta_namespace_helper = Helper(meta_namespace_proxy_class,
                                            meta_namespace_proxy_kwargs)
        self.base = base

    def new_namespace(self, **kwargs):
        t = self.base.new_namespace(**kwargs)
        return self.meta_namespace_helper.proxy(t)


# Metadef object classes
class MetadefObjectRepo(object):
    def __init__(self, base,
                 object_proxy_class=None, object_proxy_kwargs=None):
        self.base = base
        self.object_proxy_helper = Helper(object_proxy_class,
                                          object_proxy_kwargs)

    def get(self, namespace, object_name):
        meta_object = self.base.get(namespace, object_name)
        return self.object_proxy_helper.proxy(meta_object)

    def add(self, meta_object):
        self.base.add(self.object_proxy_helper.unproxy(meta_object))

    def list(self, *args, **kwargs):
        objects = self.base.list(*args, **kwargs)
        return [self.object_proxy_helper.proxy(meta_object) for meta_object
                in objects]

    def remove(self, item):
        base_item = self.object_proxy_helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.object_proxy_helper.proxy(result)

    def save(self, item):
        base_item = self.object_proxy_helper.unproxy(item)
        result = self.base.save(base_item)
        return self.object_proxy_helper.proxy(result)


class MetadefObject(object):
    def __init__(self, base):
        self.base = base
    namespace = _proxy('base', 'namespace')
    object_id = _proxy('base', 'object_id')
    name = _proxy('base', 'name')
    required = _proxy('base', 'required')
    description = _proxy('base', 'description')
    properties = _proxy('base', 'properties')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')

    def delete(self):
        self.base.delete()


class MetadefObjectFactory(object):
    def __init__(self,
                 base,
                 meta_object_proxy_class=None,
                 meta_object_proxy_kwargs=None):
        self.meta_object_helper = Helper(meta_object_proxy_class,
                                         meta_object_proxy_kwargs)
        self.base = base

    def new_object(self, **kwargs):
        t = self.base.new_object(**kwargs)
        return self.meta_object_helper.proxy(t)


# Metadef ResourceType classes
class MetadefResourceTypeRepo(object):
    def __init__(self, base, resource_type_proxy_class=None,
                 resource_type_proxy_kwargs=None):
        self.base = base
        self.resource_type_proxy_helper = Helper(resource_type_proxy_class,
                                                 resource_type_proxy_kwargs)

    def add(self, meta_resource_type):
        self.base.add(self.resource_type_proxy_helper.unproxy(
            meta_resource_type))

    def get(self, *args, **kwargs):
        resource_type = self.base.get(*args, **kwargs)
        return self.resource_type_proxy_helper.proxy(resource_type)

    def list(self, *args, **kwargs):
        resource_types = self.base.list(*args, **kwargs)
        return [self.resource_type_proxy_helper.proxy(resource_type)
                for resource_type in resource_types]

    def remove(self, item):
        base_item = self.resource_type_proxy_helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.resource_type_proxy_helper.proxy(result)


class MetadefResourceType(object):
    def __init__(self, base):
        self.base = base
    namespace = _proxy('base', 'namespace')
    name = _proxy('base', 'name')
    prefix = _proxy('base', 'prefix')
    properties_target = _proxy('base', 'properties_target')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')

    def delete(self):
        self.base.delete()


class MetadefResourceTypeFactory(object):
    def __init__(self,
                 base,
                 resource_type_proxy_class=None,
                 resource_type_proxy_kwargs=None):
        self.resource_type_helper = Helper(resource_type_proxy_class,
                                           resource_type_proxy_kwargs)
        self.base = base

    def new_resource_type(self, **kwargs):
        t = self.base.new_resource_type(**kwargs)
        return self.resource_type_helper.proxy(t)


# Metadef namespace property classes
class MetadefPropertyRepo(object):
    def __init__(self, base,
                 property_proxy_class=None, property_proxy_kwargs=None):
        self.base = base
        self.property_proxy_helper = Helper(property_proxy_class,
                                            property_proxy_kwargs)

    def get(self, namespace, property_name):
        property = self.base.get(namespace, property_name)
        return self.property_proxy_helper.proxy(property)

    def add(self, property):
        self.base.add(self.property_proxy_helper.unproxy(property))

    def list(self, *args, **kwargs):
        properties = self.base.list(*args, **kwargs)
        return [self.property_proxy_helper.proxy(property) for property
                in properties]

    def remove(self, item):
        base_item = self.property_proxy_helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.property_proxy_helper.proxy(result)

    def save(self, item):
        base_item = self.property_proxy_helper.unproxy(item)
        result = self.base.save(base_item)
        return self.property_proxy_helper.proxy(result)


class MetadefProperty(object):
    def __init__(self, base):
        self.base = base
    namespace = _proxy('base', 'namespace')
    property_id = _proxy('base', 'property_id')
    name = _proxy('base', 'name')
    schema = _proxy('base', 'schema')

    def delete(self):
        self.base.delete()


class MetadefPropertyFactory(object):
    def __init__(self,
                 base,
                 property_proxy_class=None,
                 property_proxy_kwargs=None):
        self.meta_object_helper = Helper(property_proxy_class,
                                         property_proxy_kwargs)
        self.base = base

    def new_namespace_property(self, **kwargs):
        t = self.base.new_namespace_property(**kwargs)
        return self.meta_object_helper.proxy(t)


# Metadef tag classes
class MetadefTagRepo(object):
    def __init__(self, base,
                 tag_proxy_class=None, tag_proxy_kwargs=None):
        self.base = base
        self.tag_proxy_helper = Helper(tag_proxy_class,
                                       tag_proxy_kwargs)

    def get(self, namespace, name):
        meta_tag = self.base.get(namespace, name)
        return self.tag_proxy_helper.proxy(meta_tag)

    def add(self, meta_tag):
        self.base.add(self.tag_proxy_helper.unproxy(meta_tag))

    def add_tags(self, meta_tags):
        tags_list = []
        for meta_tag in meta_tags:
            tags_list.append(self.tag_proxy_helper.unproxy(meta_tag))
        self.base.add_tags(tags_list)

    def list(self, *args, **kwargs):
        tags = self.base.list(*args, **kwargs)
        return [self.tag_proxy_helper.proxy(meta_tag) for meta_tag
                in tags]

    def remove(self, item):
        base_item = self.tag_proxy_helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.tag_proxy_helper.proxy(result)

    def save(self, item):
        base_item = self.tag_proxy_helper.unproxy(item)
        result = self.base.save(base_item)
        return self.tag_proxy_helper.proxy(result)


class MetadefTag(object):
    def __init__(self, base):
        self.base = base

    namespace = _proxy('base', 'namespace')
    tag_id = _proxy('base', 'tag_id')
    name = _proxy('base', 'name')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')

    def delete(self):
        self.base.delete()


class MetadefTagFactory(object):
    def __init__(self,
                 base,
                 meta_tag_proxy_class=None,
                 meta_tag_proxy_kwargs=None):
        self.meta_tag_helper = Helper(meta_tag_proxy_class,
                                      meta_tag_proxy_kwargs)
        self.base = base

    def new_tag(self, **kwargs):
        t = self.base.new_tag(**kwargs)
        return self.meta_tag_helper.proxy(t)
