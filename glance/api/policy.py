# Copyright (c) 2011 OpenStack Foundation
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

"""Policy Engine For Glance"""

from collections import abc
import copy

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import policy

from glance.common import exception
import glance.domain.proxy
from glance.i18n import _
from glance import policies


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
_ENFORCER = None


class Enforcer(policy.Enforcer):
    """Responsible for loading and enforcing rules"""

    def __init__(self):
        super(Enforcer, self).__init__(CONF, use_conf=True, overwrite=False)
        self.register_defaults(policies.list_rules())

    def add_rules(self, rules):
        """Add new rules to the Rules object"""
        self.set_rules(rules, overwrite=False, use_conf=self.use_conf)

    def enforce(self, context, action, target, registered=True):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        if registered and action not in self.registered_rules:
            raise policy.PolicyNotRegistered(action)
        return super(Enforcer, self).enforce(action, target,
                                             context.to_policy_values(),
                                             do_raise=True,
                                             exc=exception.Forbidden,
                                             action=action)

    def check(self, context, action, target, registered=True):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        if registered and action not in self.registered_rules:
            raise policy.PolicyNotRegistered(action)
        return super(Enforcer, self).enforce(action,
                                             target,
                                             context.to_policy_values())

    def check_is_admin(self, context):
        """Check if the given context is associated with an admin role,
           as defined via the 'context_is_admin' RBAC rule.

           :param context: Glance request context
           :returns: A non-False value if context role is admin.
        """
        return self.check(context, 'context_is_admin', context.to_dict())


def get_enforcer():
    CONF([], project='glance')
    global _ENFORCER
    if _ENFORCER is None:
        _ENFORCER = Enforcer()
    return _ENFORCER


class ImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context, policy):
        self.context = context
        self.policy = policy
        self.image_repo = image_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(ImageRepoProxy, self).__init__(image_repo,
                                             item_proxy_class=ImageProxy,
                                             item_proxy_kwargs=proxy_kwargs)

    def get(self, image_id):
        try:
            image = super(ImageRepoProxy, self).get(image_id)
        except exception.NotFound:
            self.policy.enforce(self.context, 'get_image', {})
            raise
        else:
            self.policy.enforce(self.context, 'get_image',
                                dict(ImageTarget(image)))
        return image

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_images', {})
        return super(ImageRepoProxy, self).list(*args, **kwargs)

    def save(self, image, from_state=None):
        self.policy.enforce(self.context, 'modify_image', dict(image.target))
        return super(ImageRepoProxy, self).save(image, from_state=from_state)

    def add(self, image):
        self.policy.enforce(self.context, 'add_image', dict(image.target))
        return super(ImageRepoProxy, self).add(image)


def _enforce_image_visibility(policy, context, visibility, target):
    if visibility == 'public':
        policy.enforce(context, 'publicize_image', target)
    elif visibility == 'community':
        policy.enforce(context, 'communitize_image', target)


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, policy):
        self.image = image
        self.target = ImageTarget(image)
        self.context = context
        self.policy = policy
        super(ImageProxy, self).__init__(image)

    @property
    def visibility(self):
        return self.image.visibility

    @visibility.setter
    def visibility(self, value):
        _enforce_image_visibility(self.policy, self.context, value,
                                  self.target)
        self.image.visibility = value

    @property
    def locations(self):
        return ImageLocationsProxy(self.image.locations,
                                   self.context, self.policy)

    @locations.setter
    def locations(self, value):
        if not isinstance(value, (list, ImageLocationsProxy)):
            raise exception.Invalid(_('Invalid locations: %s') % value)
        self.policy.enforce(self.context, 'set_image_location', self.target)
        new_locations = list(value)
        if (set([loc['url'] for loc in self.image.locations]) -
                set([loc['url'] for loc in new_locations])):
            self.policy.enforce(self.context, 'delete_image_location',
                                self.target)
        self.image.locations = new_locations

    def delete(self):
        self.policy.enforce(self.context, 'delete_image', dict(self.target))
        return self.image.delete()

    def deactivate(self):
        LOG.debug('Attempting deactivate')
        target = ImageTarget(self.image)
        self.policy.enforce(self.context, 'deactivate', target=target)
        LOG.debug('Deactivate allowed, continue')
        self.image.deactivate()

    def reactivate(self):
        LOG.debug('Attempting reactivate')
        target = ImageTarget(self.image)
        self.policy.enforce(self.context, 'reactivate', target=target)
        LOG.debug('Reactivate allowed, continue')
        self.image.reactivate()

    def get_data(self, *args, **kwargs):
        self.policy.enforce(self.context, 'download_image', self.target)
        return self.image.get_data(*args, **kwargs)

    def set_data(self, *args, **kwargs):
        return self.image.set_data(*args, **kwargs)


class ImageMemberProxy(glance.domain.proxy.ImageMember):

    def __init__(self, image_member, context, policy):
        super(ImageMemberProxy, self).__init__(image_member)
        self.image_member = image_member
        self.context = context
        self.policy = policy


class ImageFactoryProxy(glance.domain.proxy.ImageFactory):

    def __init__(self, image_factory, context, policy):
        self.image_factory = image_factory
        self.context = context
        self.policy = policy
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(ImageFactoryProxy, self).__init__(image_factory,
                                                proxy_class=ImageProxy,
                                                proxy_kwargs=proxy_kwargs)

    def new_image(self, **kwargs):
        _enforce_image_visibility(self.policy, self.context,
                                  kwargs.get('visibility'), {})
        return super(ImageFactoryProxy, self).new_image(**kwargs)


class ImageMemberFactoryProxy(glance.domain.proxy.ImageMembershipFactory):

    def __init__(self, member_factory, context, policy):
        super(ImageMemberFactoryProxy, self).__init__(
            member_factory,
            proxy_class=ImageMemberProxy,
            proxy_kwargs={'context': context, 'policy': policy})


class ImageMemberRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, member_repo, image, context, policy):
        self.member_repo = member_repo
        self.image = image
        self.target = ImageTarget(image)
        self.context = context
        self.policy = policy

    def add(self, member):
        self.policy.enforce(self.context, 'add_member', self.target)
        self.member_repo.add(member)

    def get(self, member_id):
        self.policy.enforce(self.context, 'get_member', self.target)
        return self.member_repo.get(member_id)

    def save(self, member, from_state=None):
        self.policy.enforce(self.context, 'modify_member', self.target)
        self.member_repo.save(member, from_state=from_state)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_members', self.target)
        return self.member_repo.list(*args, **kwargs)

    def remove(self, member):
        self.policy.enforce(self.context, 'delete_member', self.target)
        self.member_repo.remove(member)


class ImageLocationsProxy(object):

    __hash__ = None

    def __init__(self, locations, context, policy):
        self.locations = locations
        self.context = context
        self.policy = policy

    def __copy__(self):
        return type(self)(self.locations, self.context, self.policy)

    def __deepcopy__(self, memo):
        # NOTE(zhiyan): Only copy location entries, others can be reused.
        return type(self)(copy.deepcopy(self.locations, memo),
                          self.context, self.policy)

    def _get_checker(action, func_name):
        def _checker(self, *args, **kwargs):
            self.policy.enforce(self.context, action, {})
            method = getattr(self.locations, func_name)
            return method(*args, **kwargs)
        return _checker

    count = _get_checker('get_image_location', 'count')
    index = _get_checker('get_image_location', 'index')
    __getitem__ = _get_checker('get_image_location', '__getitem__')
    __contains__ = _get_checker('get_image_location', '__contains__')
    __len__ = _get_checker('get_image_location', '__len__')
    __cast = _get_checker('get_image_location', '__cast')
    __cmp__ = _get_checker('get_image_location', '__cmp__')
    __iter__ = _get_checker('get_image_location', '__iter__')

    append = _get_checker('set_image_location', 'append')
    extend = _get_checker('set_image_location', 'extend')
    insert = _get_checker('set_image_location', 'insert')
    reverse = _get_checker('set_image_location', 'reverse')
    __iadd__ = _get_checker('set_image_location', '__iadd__')
    __setitem__ = _get_checker('set_image_location', '__setitem__')

    pop = _get_checker('delete_image_location', 'pop')
    remove = _get_checker('delete_image_location', 'remove')
    __delitem__ = _get_checker('delete_image_location', '__delitem__')
    __delslice__ = _get_checker('delete_image_location', '__delslice__')

    del _get_checker


class TaskProxy(glance.domain.proxy.Task):

    def __init__(self, task, context, policy):
        self.task = task
        self.context = context
        self.policy = policy
        super(TaskProxy, self).__init__(task)


class TaskStubProxy(glance.domain.proxy.TaskStub):

    def __init__(self, task_stub, context, policy):
        self.task_stub = task_stub
        self.context = context
        self.policy = policy
        super(TaskStubProxy, self).__init__(task_stub)


class TaskRepoProxy(glance.domain.proxy.TaskRepo):

    def __init__(self, task_repo, context, task_policy):
        self.context = context
        self.policy = task_policy
        self.task_repo = task_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(TaskRepoProxy,
              self).__init__(task_repo,
                             task_proxy_class=TaskProxy,
                             task_proxy_kwargs=proxy_kwargs)

    def get(self, task_id):
        self.policy.enforce(self.context, 'get_task', {})
        return super(TaskRepoProxy, self).get(task_id)

    def add(self, task):
        self.policy.enforce(self.context, 'add_task', {})
        super(TaskRepoProxy, self).add(task)

    def save(self, task):
        self.policy.enforce(self.context, 'modify_task', {})
        super(TaskRepoProxy, self).save(task)


class TaskStubRepoProxy(glance.domain.proxy.TaskStubRepo):

    def __init__(self, task_stub_repo, context, task_policy):
        self.context = context
        self.policy = task_policy
        self.task_stub_repo = task_stub_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(TaskStubRepoProxy,
              self).__init__(task_stub_repo,
                             task_stub_proxy_class=TaskStubProxy,
                             task_stub_proxy_kwargs=proxy_kwargs)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_tasks', {})
        return super(TaskStubRepoProxy, self).list(*args, **kwargs)


class TaskFactoryProxy(glance.domain.proxy.TaskFactory):

    def __init__(self, task_factory, context, policy):
        self.task_factory = task_factory
        self.context = context
        self.policy = policy
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(TaskFactoryProxy, self).__init__(
            task_factory,
            task_proxy_class=TaskProxy,
            task_proxy_kwargs=proxy_kwargs)


class ImageTarget(abc.Mapping):
    SENTINEL = object()

    def __init__(self, target):
        """Initialize the object

        :param target: Object being targeted
        """
        self.target = target
        self._target_keys = [k for k in dir(ImageProxy)
                             if not k.startswith('__')
                             if not callable(getattr(ImageProxy, k))]

    def __getitem__(self, key):
        """Return the value of 'key' from the target.

        If the target has the attribute 'key', return it.

        :param key: value to retrieve
        """
        key = self.key_transforms(key)

        value = getattr(self.target, key, self.SENTINEL)
        if value is self.SENTINEL:
            extra_properties = getattr(self.target, 'extra_properties', None)
            if extra_properties is not None:
                value = extra_properties[key]
            else:
                value = None
        return value

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __len__(self):
        length = len(self._target_keys)
        length += len(getattr(self.target, 'extra_properties', {}))
        return length

    def __iter__(self):
        for key in self._target_keys:
            yield key
        for key in getattr(self.target, 'extra_properties', {}).keys():
            yield key

    def key_transforms(self, key):
        if key == 'id':
            key = 'image_id'

        return key


# Metadef Namespace classes
class MetadefNamespaceProxy(glance.domain.proxy.MetadefNamespace):

    def __init__(self, namespace, context, policy):
        self.namespace_input = namespace
        self.context = context
        self.policy = policy
        super(MetadefNamespaceProxy, self).__init__(namespace)

    def delete(self):
        self.policy.enforce(self.context, 'delete_metadef_namespace', {})
        return super(MetadefNamespaceProxy, self).delete()


class MetadefNamespaceRepoProxy(glance.domain.proxy.MetadefNamespaceRepo):

    def __init__(self, namespace_repo, context, namespace_policy):
        self.context = context
        self.policy = namespace_policy
        self.namespace_repo = namespace_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefNamespaceRepoProxy,
              self).__init__(namespace_repo,
                             namespace_proxy_class=MetadefNamespaceProxy,
                             namespace_proxy_kwargs=proxy_kwargs)

    def get(self, namespace):
        self.policy.enforce(self.context, 'get_metadef_namespace', {})
        return super(MetadefNamespaceRepoProxy, self).get(namespace)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_metadef_namespaces', {})
        return super(MetadefNamespaceRepoProxy, self).list(*args, **kwargs)

    def save(self, namespace):
        self.policy.enforce(self.context, 'modify_metadef_namespace', {})
        return super(MetadefNamespaceRepoProxy, self).save(namespace)

    def add(self, namespace):
        self.policy.enforce(self.context, 'add_metadef_namespace', {})
        return super(MetadefNamespaceRepoProxy, self).add(namespace)

    def remove(self, namespace):
        self.policy.enforce(self.context, 'delete_metadef_namespace', {})
        return super(MetadefNamespaceRepoProxy, self).remove(namespace)

    def remove_tags(self, namespace):
        self.policy.enforce(self.context, 'delete_metadef_tags', {})
        return super(MetadefNamespaceRepoProxy, self).remove_tags(namespace)


class MetadefNamespaceFactoryProxy(
        glance.domain.proxy.MetadefNamespaceFactory):

    def __init__(self, meta_namespace_factory, context, policy):
        self.meta_namespace_factory = meta_namespace_factory
        self.context = context
        self.policy = policy
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefNamespaceFactoryProxy, self).__init__(
            meta_namespace_factory,
            meta_namespace_proxy_class=MetadefNamespaceProxy,
            meta_namespace_proxy_kwargs=proxy_kwargs)


# Metadef Object classes
class MetadefObjectProxy(glance.domain.proxy.MetadefObject):

    def __init__(self, meta_object, context, policy):
        self.meta_object = meta_object
        self.context = context
        self.policy = policy
        super(MetadefObjectProxy, self).__init__(meta_object)

    def delete(self):
        self.policy.enforce(self.context, 'delete_metadef_object', {})
        return super(MetadefObjectProxy, self).delete()


class MetadefObjectRepoProxy(glance.domain.proxy.MetadefObjectRepo):

    def __init__(self, object_repo, context, object_policy):
        self.context = context
        self.policy = object_policy
        self.object_repo = object_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefObjectRepoProxy,
              self).__init__(object_repo,
                             object_proxy_class=MetadefObjectProxy,
                             object_proxy_kwargs=proxy_kwargs)

    def get(self, namespace, object_name):
        self.policy.enforce(self.context, 'get_metadef_object', {})
        return super(MetadefObjectRepoProxy, self).get(namespace, object_name)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_metadef_objects', {})
        return super(MetadefObjectRepoProxy, self).list(*args, **kwargs)

    def save(self, meta_object):
        self.policy.enforce(self.context, 'modify_metadef_object', {})
        return super(MetadefObjectRepoProxy, self).save(meta_object)

    def add(self, meta_object):
        self.policy.enforce(self.context, 'add_metadef_object', {})
        return super(MetadefObjectRepoProxy, self).add(meta_object)

    def remove(self, meta_object):
        self.policy.enforce(self.context, 'delete_metadef_object', {})
        return super(MetadefObjectRepoProxy, self).remove(meta_object)


class MetadefObjectFactoryProxy(glance.domain.proxy.MetadefObjectFactory):

    def __init__(self, meta_object_factory, context, policy):
        self.meta_object_factory = meta_object_factory
        self.context = context
        self.policy = policy
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefObjectFactoryProxy, self).__init__(
            meta_object_factory,
            meta_object_proxy_class=MetadefObjectProxy,
            meta_object_proxy_kwargs=proxy_kwargs)


# Metadef ResourceType classes
class MetadefResourceTypeProxy(glance.domain.proxy.MetadefResourceType):

    def __init__(self, meta_resource_type, context, policy):
        self.meta_resource_type = meta_resource_type
        self.context = context
        self.policy = policy
        super(MetadefResourceTypeProxy, self).__init__(meta_resource_type)

    def delete(self):
        self.policy.enforce(self.context,
                            'remove_metadef_resource_type_association', {})
        return super(MetadefResourceTypeProxy, self).delete()


class MetadefResourceTypeRepoProxy(
        glance.domain.proxy.MetadefResourceTypeRepo):

    def __init__(self, resource_type_repo, context, resource_type_policy):
        self.context = context
        self.policy = resource_type_policy
        self.resource_type_repo = resource_type_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefResourceTypeRepoProxy, self).__init__(
            resource_type_repo,
            resource_type_proxy_class=MetadefResourceTypeProxy,
            resource_type_proxy_kwargs=proxy_kwargs)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'list_metadef_resource_types', {})
        return super(MetadefResourceTypeRepoProxy, self).list(*args, **kwargs)

    def get(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_metadef_resource_type', {})
        return super(MetadefResourceTypeRepoProxy, self).get(*args, **kwargs)

    def add(self, resource_type):
        self.policy.enforce(self.context,
                            'add_metadef_resource_type_association', {})
        return super(MetadefResourceTypeRepoProxy, self).add(resource_type)

    def remove(self, *args, **kwargs):
        self.policy.enforce(self.context,
                            'remove_metadef_resource_type_association', {})
        return super(MetadefResourceTypeRepoProxy,
                     self).remove(*args, **kwargs)


class MetadefResourceTypeFactoryProxy(
        glance.domain.proxy.MetadefResourceTypeFactory):

    def __init__(self, resource_type_factory, context, policy):
        self.resource_type_factory = resource_type_factory
        self.context = context
        self.policy = policy
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefResourceTypeFactoryProxy, self).__init__(
            resource_type_factory,
            resource_type_proxy_class=MetadefResourceTypeProxy,
            resource_type_proxy_kwargs=proxy_kwargs)


# Metadef namespace properties classes
class MetadefPropertyProxy(glance.domain.proxy.MetadefProperty):

    def __init__(self, namespace_property, context, policy):
        self.namespace_property = namespace_property
        self.context = context
        self.policy = policy
        super(MetadefPropertyProxy, self).__init__(namespace_property)

    def delete(self):
        self.policy.enforce(self.context, 'remove_metadef_property', {})
        return super(MetadefPropertyProxy, self).delete()


class MetadefPropertyRepoProxy(glance.domain.proxy.MetadefPropertyRepo):

    def __init__(self, property_repo, context, object_policy):
        self.context = context
        self.policy = object_policy
        self.property_repo = property_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefPropertyRepoProxy, self).__init__(
            property_repo,
            property_proxy_class=MetadefPropertyProxy,
            property_proxy_kwargs=proxy_kwargs)

    def get(self, namespace, property_name):
        self.policy.enforce(self.context, 'get_metadef_property', {})
        return super(MetadefPropertyRepoProxy, self).get(namespace,
                                                         property_name)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_metadef_properties', {})
        return super(MetadefPropertyRepoProxy, self).list(
            *args, **kwargs)

    def save(self, namespace_property):
        self.policy.enforce(self.context, 'modify_metadef_property', {})
        return super(MetadefPropertyRepoProxy, self).save(
            namespace_property)

    def add(self, namespace_property):
        self.policy.enforce(self.context, 'add_metadef_property', {})
        return super(MetadefPropertyRepoProxy, self).add(
            namespace_property)

    def remove(self, *args, **kwargs):
        self.policy.enforce(self.context, 'remove_metadef_property', {})
        return super(MetadefPropertyRepoProxy, self).remove(*args, **kwargs)


class MetadefPropertyFactoryProxy(glance.domain.proxy.MetadefPropertyFactory):

    def __init__(self, namespace_property_factory, context, policy):
        self.namespace_property_factory = namespace_property_factory
        self.context = context
        self.policy = policy
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefPropertyFactoryProxy, self).__init__(
            namespace_property_factory,
            property_proxy_class=MetadefPropertyProxy,
            property_proxy_kwargs=proxy_kwargs)


# Metadef Tag classes
class MetadefTagProxy(glance.domain.proxy.MetadefTag):

    def __init__(self, meta_tag, context, policy):
        self.context = context
        self.policy = policy
        super(MetadefTagProxy, self).__init__(meta_tag)

    def delete(self):
        self.policy.enforce(self.context, 'delete_metadef_tag', {})
        return super(MetadefTagProxy, self).delete()


class MetadefTagRepoProxy(glance.domain.proxy.MetadefTagRepo):

    def __init__(self, tag_repo, context, tag_policy):
        self.context = context
        self.policy = tag_policy
        self.tag_repo = tag_repo
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefTagRepoProxy,
              self).__init__(tag_repo,
                             tag_proxy_class=MetadefTagProxy,
                             tag_proxy_kwargs=proxy_kwargs)

    def get(self, namespace, tag_name):
        self.policy.enforce(self.context, 'get_metadef_tag', {})
        return super(MetadefTagRepoProxy, self).get(namespace, tag_name)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_metadef_tags', {})
        return super(MetadefTagRepoProxy, self).list(*args, **kwargs)

    def save(self, meta_tag):
        self.policy.enforce(self.context, 'modify_metadef_tag', {})
        return super(MetadefTagRepoProxy, self).save(meta_tag)

    def add(self, meta_tag):
        self.policy.enforce(self.context, 'add_metadef_tag', {})
        return super(MetadefTagRepoProxy, self).add(meta_tag)

    def add_tags(self, meta_tags):
        self.policy.enforce(self.context, 'add_metadef_tags', {})
        return super(MetadefTagRepoProxy, self).add_tags(meta_tags)

    def remove(self, meta_tag):
        self.policy.enforce(self.context, 'delete_metadef_tag', {})
        return super(MetadefTagRepoProxy, self).remove(meta_tag)


class MetadefTagFactoryProxy(glance.domain.proxy.MetadefTagFactory):

    def __init__(self, meta_tag_factory, context, policy):
        self.meta_tag_factory = meta_tag_factory
        self.context = context
        self.policy = policy
        proxy_kwargs = {'context': self.context, 'policy': self.policy}
        super(MetadefTagFactoryProxy, self).__init__(
            meta_tag_factory,
            meta_tag_proxy_class=MetadefTagProxy,
            meta_tag_proxy_kwargs=proxy_kwargs)
