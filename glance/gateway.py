# Copyright 2012 OpenStack Foundation
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

from glance.api import authorization
from glance.api import policy
import glance.db
import glance.domain
import glance.notifier
import glance.store


class Gateway(object):
    def __init__(self, db_api=None, store_api=None, notifier=None,
                 policy_enforcer=None):
        self.db_api = db_api or glance.db.get_api()
        self.db_api.setup_db_env()
        self.store_api = store_api or glance.store
        self.notifier = notifier or glance.notifier.Notifier()
        self.policy = policy_enforcer or policy.Enforcer()

    def get_image_factory(self, context):
        image_factory = glance.domain.ImageFactory()
        store_image_factory = glance.store.ImageFactoryProxy(
                image_factory, context, self.store_api)
        policy_image_factory = policy.ImageFactoryProxy(
                store_image_factory, context, self.policy)
        notifier_image_factory = glance.notifier.ImageFactoryProxy(
                policy_image_factory, context, self.notifier)
        authorized_image_factory = authorization.ImageFactoryProxy(
                notifier_image_factory, context)
        return authorized_image_factory

    def get_image_member_factory(self, context):
        image_factory = glance.domain.ImageMemberFactory()
        authorized_image_factory = authorization.ImageMemberFactoryProxy(
                                    image_factory, context)
        return authorized_image_factory

    def get_repo(self, context):
        image_repo = glance.db.ImageRepo(context, self.db_api)
        store_image_repo = glance.store.ImageRepoProxy(
                image_repo, context, self.store_api)
        policy_image_repo = policy.ImageRepoProxy(
                store_image_repo, context, self.policy)
        notifier_image_repo = glance.notifier.ImageRepoProxy(
                policy_image_repo, context, self.notifier)
        authorized_image_repo = authorization.ImageRepoProxy(
                notifier_image_repo, context)
        return authorized_image_repo
