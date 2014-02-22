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
    def __init__(self,
                 base,
                 task_proxy_class=None, task_proxy_kwargs=None,
                 task_details_proxy_class=None,
                 task_details_proxy_kwargs=None):
        self.base = base
        self.task_proxy_helper = Helper(task_proxy_class, task_proxy_kwargs)
        self.task_details_proxy_helper = Helper(task_details_proxy_class,
                                                task_details_proxy_kwargs)

    def get_task_and_details(self, task_id):
        task, task_details = self.base.get_task_and_details(task_id)
        return (self.task_proxy_helper.proxy(task),
                self.task_details_proxy_helper.proxy(task_details))

    def list_tasks(self, *args, **kwargs):
        tasks = self.base.list_tasks(*args, **kwargs)
        return [self.task_proxy_helper.proxy(task) for task in tasks]

    def add(self, task, task_details=None):
        self.base.add(self.task_proxy_helper.unproxy(task),
                      self.task_details_proxy_helper.unproxy(task_details))

    def save(self, task, task_details=None):
        self.base.save(self.task_proxy_helper.unproxy(task),
                       self.task_details_proxy_helper.unproxy(task_details))

    def remove(self, task):
        base_task = self.task_proxy_helper.unproxy(task)
        self.base.remove(base_task)


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

    def save(self, item):
        base_item = self.helper.unproxy(item)
        result = self.base.save(base_item)
        return self.helper.proxy(result)

    def remove(self, item):
        base_item = self.helper.unproxy(item)
        result = self.base.remove(base_item)
        return self.helper.proxy(result)


class ImageFactory(object):
    def __init__(self, base, proxy_class=None, proxy_kwargs=None):
        self.helper = Helper(proxy_class, proxy_kwargs)
        self.base = base

    def new_image(self, **kwargs):
        return self.helper.proxy(self.base.new_image(**kwargs))


class ImageMembershipFactory(object):
    def __init__(self, base, image_proxy_class=None, image_proxy_kwargs=None,
                 member_proxy_class=None, member_proxy_kwargs=None):
        self.base = base
        self.image_helper = Helper(image_proxy_class, image_proxy_kwargs)
        self.member_helper = Helper(member_proxy_class, member_proxy_kwargs)

    def new_image_member(self, image, member_id):
        base_image = self.image_helper.unproxy(image)
        member = self.base.new_image_member(base_image, member_id)
        return self.member_helper.proxy(member)


class Image(object):
    def __init__(self, base, member_repo_proxy_class=None,
                 member_repo_proxy_kwargs=None):
        self.base = base
        self.helper = Helper(member_repo_proxy_class,
                             member_repo_proxy_kwargs)

    name = _proxy('base', 'name')
    image_id = _proxy('base', 'image_id')
    name = _proxy('base', 'name')
    status = _proxy('base', 'status')
    created_at = _proxy('base', 'created_at')
    updated_at = _proxy('base', 'updated_at')
    visibility = _proxy('base', 'visibility')
    min_disk = _proxy('base', 'min_disk')
    min_ram = _proxy('base', 'min_ram')
    protected = _proxy('base', 'protected')
    locations = _proxy('base', 'locations')
    checksum = _proxy('base', 'checksum')
    owner = _proxy('base', 'owner')
    disk_format = _proxy('base', 'disk_format')
    container_format = _proxy('base', 'container_format')
    size = _proxy('base', 'size')
    virtual_size = _proxy('base', 'virtual_size')
    extra_properties = _proxy('base', 'extra_properties')
    tags = _proxy('base', 'tags')

    def delete(self):
        self.base.delete()

    def set_data(self, data, size=None):
        self.base.set_data(data, size)

    def get_data(self):
        return self.base.get_data()

    def get_member_repo(self):
        return self.helper.proxy(self.base.get_member_repo())


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

    def run(self, executor):
        self.base.run(executor)

    def begin_processing(self):
        self.base.begin_processing()

    def succeed(self, result):
        self.base.succeed(result)

    def fail(self, message):
        self.base.fail(message)


class TaskDetails(object):
    def __init__(self, base):
        self.base = base

    task_id = _proxy('base', 'task_id')
    input = _proxy('base', 'input')
    result = _proxy('base', 'result')
    message = _proxy('base', 'message')


class TaskFactory(object):
    def __init__(self,
                 base,
                 task_proxy_class=None,
                 task_proxy_kwargs=None,
                 task_details_proxy_class=None,
                 task_details_proxy_kwargs=None):
        self.task_helper = Helper(task_proxy_class, task_proxy_kwargs)
        self.task_details_helper = Helper(task_details_proxy_class,
                                          task_details_proxy_kwargs)
        self.base = base

    def new_task(self, **kwargs):
        t = self.base.new_task(**kwargs)
        return self.task_helper.proxy(t)

    def new_task_details(self, task_id, task_input, message=None, result=None):
        td = self.base.new_task_details(task_id, task_input, message, result)
        return self.task_details_helper.proxy(td)
