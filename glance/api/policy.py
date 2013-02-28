# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

import json
import os.path

from oslo.config import cfg

from glance.common import exception
import glance.domain.proxy
import glance.openstack.common.log as logging
from glance.openstack.common import policy

LOG = logging.getLogger(__name__)

policy_opts = [
    cfg.StrOpt('policy_file', default='policy.json'),
    cfg.StrOpt('policy_default_rule', default='default'),
]

CONF = cfg.CONF
CONF.register_opts(policy_opts)


DEFAULT_RULES = {
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

    def set_rules(self, rules):
        """Create a new Rules object based on the provided dict of rules"""
        rules_obj = policy.Rules(rules, self.default_rule)
        policy.set_rules(rules_obj)

    def load_rules(self):
        """Set the rules found in the json file on disk"""
        if self.policy_path:
            rules = self._read_policy_file()
            rule_type = ""
        else:
            rules = DEFAULT_RULES
            rule_type = "default "

        text_rules = dict((k, str(v)) for k, v in rules.items())
        LOG.debug(_('Loaded %(rule_type)spolicy rules: %(text_rules)s') %
                  locals())

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
            LOG.debug(_("Loading policy from %s") % self.policy_path)
            with open(self.policy_path) as fap:
                raw_contents = fap.read()
                rules_dict = json.loads(raw_contents)
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
        self.load_rules()

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
           :param object: Dictionary representing the object of the action.
           :raises: `glance.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        return self._check(context, action, target,
                           exception.Forbidden, action=action)

    def check(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param object: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        return self._check(context, action, target)


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

    def delete(self):
        self.policy.enforce(self.context, 'delete_image', {})
        return self.image.delete()

    def get_data(self, *args, **kwargs):
        self.policy.enforce(self.context, 'download_image', {})
        return self.image.get_data(*args, **kwargs)


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
