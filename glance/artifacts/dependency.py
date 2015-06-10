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

from glance.artifacts.domain import proxy
import glance.common.artifacts.definitions as definitions
import glance.common.exception as exc
from glance import i18n

_ = i18n._


class ArtifactProxy(proxy.Artifact):
    def __init__(self, artifact, repo):
        super(ArtifactProxy, self).__init__(artifact)
        self.artifact = artifact
        self.repo = repo

    def set_type_specific_property(self, prop_name, value):
        if prop_name not in self.metadata.attributes.dependencies:
            return super(ArtifactProxy, self).set_type_specific_property(
                prop_name, value)
        # for every dependency have to transfer dep_id into a dependency itself
        if value is None:
            setattr(self.artifact, prop_name, None)
        else:
            if not isinstance(value, list):
                setattr(self.artifact, prop_name,
                        self._fetch_dependency(value))
            else:
                setattr(self.artifact, prop_name,
                        [self._fetch_dependency(dep_id) for dep_id in value])

    def _fetch_dependency(self, dep_id):
        # check for circular dependency id -> id
        if self.id == dep_id:
            raise exc.ArtifactCircularDependency()
        art = self.repo.get(artifact_id=dep_id)

        # repo returns a proxy of some level.
        # Need to find the base declarative artifact
        while not isinstance(art, definitions.ArtifactType):
            art = art.base
        return art


class ArtifactRepo(proxy.ArtifactRepo):
    def __init__(self, repo, plugins,
                 item_proxy_class=None, item_proxy_kwargs=None):
        self.plugins = plugins
        super(ArtifactRepo, self).__init__(repo,
                                           item_proxy_class=ArtifactProxy,
                                           item_proxy_kwargs={'repo': self})

    def _check_dep_state(self, dep, state):
        """Raises an exception if dependency 'dep' is not in state 'state'"""
        if dep.state != state:
            raise exc.Invalid(_(
                "Not all dependencies are in '%s' state") % state)

    def publish(self, artifact, *args, **kwargs):
        """
        Creates transitive dependencies,
        checks that all dependencies are in active state and
        transfers artifact from creating to active state
        """
        # make sure that all required dependencies exist
        artifact.__pre_publish__(*args, **kwargs)
        # make sure that all dependencies are active
        for param in artifact.metadata.attributes.dependencies:
            dependency = getattr(artifact, param)
            if isinstance(dependency, list):
                for dep in dependency:
                    self._check_dep_state(dep, 'active')
            elif dependency:
                self._check_dep_state(dependency, 'active')
        # as state is changed on db save, have to retrieve the freshly changed
        # artifact (the one passed into the func will have old state value)
        artifact = self.base.publish(self.helper.unproxy(artifact))

        return self.helper.proxy(artifact)

    def remove(self, artifact):
        """
        Checks that artifact has no dependencies and removes it.
        Otherwise an exception is raised
        """
        for param in artifact.metadata.attributes.dependencies:
            if getattr(artifact, param):
                raise exc.Invalid(_(
                    "Dependency property '%s' has to be deleted first") %
                    param)
        return self.base.remove(self.helper.unproxy(artifact))


class ArtifactFactory(proxy.ArtifactFactory):
    def __init__(self, base, klass, repo):
        self.klass = klass
        self.repo = repo
        super(ArtifactFactory, self).__init__(
            base, artifact_proxy_class=ArtifactProxy,
            artifact_proxy_kwargs={'repo': self.repo})

    def new_artifact(self, *args, **kwargs):
        """
        Creates an artifact without dependencies first
        and then adds them to the newly created artifact
        """
        # filter dependencies
        no_deps = {p: kwargs[p] for p in kwargs
                   if p not in self.klass.metadata.attributes.dependencies}
        deps = {p: kwargs[p] for p in kwargs
                if p in self.klass.metadata.attributes.dependencies}
        artifact = super(ArtifactFactory, self).new_artifact(*args, **no_deps)
        # now set dependencies
        for dep_param, dep_value in deps.iteritems():
            setattr(artifact, dep_param, dep_value)
        return artifact
