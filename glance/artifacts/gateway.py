# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import glance_store

from glance.artifacts import dependency
from glance.artifacts import domain
from glance.artifacts import location
from glance.artifacts import updater
from glance.common import store_utils
import glance.db


class Gateway(object):
    def __init__(self, db_api=None, store_api=None, plugins=None):
        self.db_api = db_api or glance.db.get_api()
        self.store_api = store_api or glance_store
        self.store_utils = store_utils
        self.plugins = plugins

    def get_artifact_type_factory(self, context, klass):
        declarative_factory = domain.ArtifactFactory(context, klass)
        repo = self.get_artifact_repo(context)
        dependencies_factory = dependency.ArtifactFactory(declarative_factory,
                                                          klass, repo)
        factory = location.ArtifactFactoryProxy(dependencies_factory,
                                                context,
                                                self.store_api,
                                                self.store_utils)
        updater_factory = updater.ArtifactFactoryProxy(factory)
        return updater_factory

    def get_artifact_repo(self, context):
        artifact_repo = glance.db.ArtifactRepo(context,
                                               self.db_api,
                                               self.plugins)
        dependencies_repo = dependency.ArtifactRepo(artifact_repo,
                                                    self.plugins)
        repo = location.ArtifactRepoProxy(dependencies_repo,
                                          context,
                                          self.store_api,
                                          self.store_utils)
        updater_repo = updater.ArtifactRepoProxy(repo)
        return updater_repo
