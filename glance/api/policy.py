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

import copy
import os.path

from oslo.config import cfg

from glance.common import exception
import glance.domain.proxy
from glance.openstack.common import jsonutils
import glance.openstack.common.log as logging
from glance.openstack.common import policy

LOG = logging.getLogger(__name__)

policy_opts = [
    cfg.StrOpt('policy_file', default='policy.json',
               help=_('The location of the policy file.')),
    cfg.StrOpt('policy_default_rule', default='default',
               help=_('The default policy to use.')),
]

CONF = cfg.CONF
CONF.register_opts(policy_opts)


DEFAULT_RULES = {
    'context_is_admin': policy.RoleCheck('role', 'admin'),
    'default': policy.TrueCheck(),
    'manage_image_cache': policy.RoleCheck('role', 'admin'),
}


class Enforcer(object):
    """Responsible for loading and enforcing rules"""

    def __init__(self):
        self.default_rule = CONF.policy_default_rule
        self.policy_path = self._find_policy_file()
        self.policy_file_mtime = None
        self.policy_file_contents = None
        self.load_rules()

    def set_rules(self, rules):
        """Create a new Rules object based on the provided dict of rules"""
        rules_obj = policy.Rules(rules, self.default_rule)
        policy.set_rules(rules_obj)

    def add_rules(self, rules):
        """Add new rules to the Rules object"""
        if policy._rules:
            rules_obj = policy.Rules(rules)
            policy._rules.update(rules_obj)
        else:
            self.set_rules(rules)

    def load_rules(self):
        """Set the rules found in the json file on disk"""
        if self.policy_path:
            rules = self._read_policy_file()
            rule_type = ""
        else:
            rules = DEFAULT_RULES
            rule_type = "default "

        text_rules = dict((k, str(v)) for k, v in rules.items())
        msg = ('Loaded %(rule_type)spolicy rules: %(text_rules)s' %
               {'rule_type': rule_type, 'text_rules': text_rules})
        LOG.debug(msg)

        self.set_rules(rules)

    @staticmethod
    def _find_policy_file():
        """Locate the policy json data file"""
        policy_file = CONF.find_file(CONF.policy_file)
        if policy_file:
            return policy_file
        else:
            LOG.warn(_('Unable to find policy file'))
            return None

    def _read_policy_file(self):
        """Read contents of the policy file

        This re-caches policy data if the file has been changed.
        """
        mtime = os.path.getmtime(self.policy_path)
        if not self.policy_file_contents or mtime != self.policy_file_mtime:
            LOG.debug("Loading policy from %s" % self.policy_path)
            with open(self.policy_path) as fap:
                raw_contents = fap.read()
                rules_dict = jsonutils.loads(raw_contents)
                self.policy_file_contents = dict(
                    (k, policy.parse_rule(v))
                    for k, v in rules_dict.items())
            self.policy_file_mtime = mtime
        return self.policy_file_contents

    def _check(self, context, rule, target, *args, **kwargs):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param rule: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        credentials = {
            'roles': context.roles,
            'user': context.user,
            'tenant': context.tenant,
        }

        return policy.check(rule, target, credentials, *args, **kwargs)

    def enforce(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        return self._check(context, action, target,
                           exception.Forbidden, action=action)

    def check(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        return self._check(context, action, target)

    def check_is_admin(self, context):
        """Check if the given context is associated with an admin role,
           as defined via the 'context_is_admin' RBAC rule.

           :param context: Glance request context
           :returns: A non-False value if context role is admin.
        """
        target = context.to_dict()
        return self.check(context, 'context_is_admin', target)


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
        self.policy.enforce(self.context, 'get_image', {})
        return super(ImageRepoProxy, self).get(image_id)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_images', {})
        return super(ImageRepoProxy, self).list(*args, **kwargs)

    def save(self, image):
        self.policy.enforce(self.context, 'modify_image', {})
        return super(ImageRepoProxy, self).save(image)

    def add(self, image):
        self.policy.enforce(self.context, 'add_image', {})
        return super(ImageRepoProxy, self).add(image)


class ImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, policy):
        self.image = image
        self.context = context
        self.policy = policy
        super(ImageProxy, self).__init__(image)

    @property
    def visibility(self):
        return self.image.visibility

    @visibility.setter
    def visibility(self, value):
        if value == 'public':
            self.policy.enforce(self.context, 'publicize_image', {})
        self.image.visibility = value

    @property
    def locations(self):
        return ImageLocationsProxy(self.image.locations,
                                   self.context, self.policy)

    @locations.setter
    def locations(self, value):
        if not isinstance(value, (list, ImageLocationsProxy)):
            raise exception.Invalid(_('Invalid locations: %s') % value)
        self.policy.enforce(self.context, 'set_image_location', {})
        new_locations = list(value)
        if (set([loc['url'] for loc in self.image.locations]) -
                set([loc['url'] for loc in new_locations])):
            self.policy.enforce(self.context, 'delete_image_location', {})
        self.image.locations = new_locations

    def delete(self):
        self.policy.enforce(self.context, 'delete_image', {})
        return self.image.delete()

    def get_data(self, *args, **kwargs):
        target = ImageTarget(self.image)
        self.policy.enforce(self.context, 'download_image',
                            target=target)
        return self.image.get_data(*args, **kwargs)

    def set_data(self, *args, **kwargs):
        self.policy.enforce(self.context, 'upload_image', {})
        return self.image.set_data(*args, **kwargs)

    def get_member_repo(self, **kwargs):
        member_repo = self.image.get_member_repo(**kwargs)
        return ImageMemberRepoProxy(member_repo, self.context, self.policy)


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
        if kwargs.get('visibility') == 'public':
            self.policy.enforce(self.context, 'publicize_image', {})
        return super(ImageFactoryProxy, self).new_image(**kwargs)


class ImageMemberFactoryProxy(glance.domain.proxy.ImageMembershipFactory):

    def __init__(self, member_factory, context, policy):
        super(ImageMemberFactoryProxy, self).__init__(
            member_factory,
            image_proxy_class=ImageProxy,
            image_proxy_kwargs={'context': context, 'policy': policy})


class ImageMemberRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, member_repo, context, policy):
        self.member_repo = member_repo
        self.context = context
        self.policy = policy

    def add(self, member):
        self.policy.enforce(self.context, 'add_member', {})
        self.member_repo.add(member)

    def get(self, member_id):
        self.policy.enforce(self.context, 'get_member', {})
        return self.member_repo.get(member_id)

    def save(self, member):
        self.policy.enforce(self.context, 'modify_member', {})
        self.member_repo.save(member)

    def list(self, *args, **kwargs):
        self.policy.enforce(self.context, 'get_members', {})
        return self.member_repo.list(*args, **kwargs)

    def remove(self, member):
        self.policy.enforce(self.context, 'delete_member', {})
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
            assert hasattr(self.locations, func_name)
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


class ImageTarget(object):

    def __init__(self, image):
        """
        Initialize the object

        :param image: Image object
        """
        self.image = image

    def __getitem__(self, key):
        """
        Returns the value of 'key' from the image if image has that attribute
        else tries to retrieve value from the extra_properties of image.

        :param key: value to retrieve
        """
        # Need to change the key 'id' to 'image_id' as Image object has
        # attribute as 'image_id' in case of V2.
        if key == 'id':
            key = 'image_id'

        if hasattr(self.image, key):
            return getattr(self.image, key)
        else:
            return self.image.extra_properties[key]


#Metadef Namespace classes
class MetadefNamespaceProxy(glance.domain.proxy.MetadefNamespace):

    def __init__(self, namespace, context, policy):
        self.namespace_input = namespace
        self.context = context
        self.policy = policy
        super(MetadefNamespaceProxy, self).__init__(namespace)


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


#Metadef Object classes
class MetadefObjectProxy(glance.domain.proxy.MetadefObject):

    def __init__(self, meta_object, context, policy):
        self.meta_object = meta_object
        self.context = context
        self.policy = policy
        super(MetadefObjectProxy, self).__init__(meta_object)


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


#Metadef ResourceType classes
class MetadefResourceTypeProxy(glance.domain.proxy.MetadefResourceType):

    def __init__(self, meta_resource_type, context, policy):
        self.meta_resource_type = meta_resource_type
        self.context = context
        self.policy = policy
        super(MetadefResourceTypeProxy, self).__init__(meta_resource_type)


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

    def add(self, resource_type):
        self.policy.enforce(self.context,
                            'add_metadef_resource_type_association', {})
        return super(MetadefResourceTypeRepoProxy, self).add(resource_type)


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


#Metadef namespace properties classes
class MetadefPropertyProxy(glance.domain.proxy.MetadefProperty):

    def __init__(self, namespace_property, context, policy):
        self.namespace_property = namespace_property
        self.context = context
        self.policy = policy
        super(MetadefPropertyProxy, self).__init__(namespace_property)


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
