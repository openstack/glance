#    Copyright 2013 Rackspace
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

from glance.common import exception
import glance.domain.proxy


class ProtectedImageFactoryProxy(glance.domain.proxy.ImageFactory):

    def __init__(self, image_factory, context, property_rules):
        self.image_factory = image_factory
        self.context = context
        self.property_rules = property_rules
        kwargs = {'context': self.context,
                  'property_rules': self.property_rules}
        super(ProtectedImageFactoryProxy, self).__init__(
            image_factory,
            proxy_class=ProtectedImageProxy,
            proxy_kwargs=kwargs)

    def new_image(self, **kwargs):
        extra_props = kwargs.pop('extra_properties', {})

        extra_properties = {}
        for key in extra_props.keys():
            if self.property_rules.check_property_rules(key, 'create',
                                                        self.context):
                extra_properties[key] = extra_props[key]
            else:
                raise exception.ReservedProperty(property=key)
        return super(ProtectedImageFactoryProxy, self).new_image(
            extra_properties=extra_properties, **kwargs)


class ProtectedImageRepoProxy(glance.domain.proxy.Repo):

    def __init__(self, image_repo, context, property_rules):
        self.context = context
        self.image_repo = image_repo
        self.property_rules = property_rules
        proxy_kwargs = {'context': self.context}
        super(ProtectedImageRepoProxy, self).__init__(
            image_repo, item_proxy_class=ProtectedImageProxy,
            item_proxy_kwargs=proxy_kwargs)

    def get(self, image_id):
        return ProtectedImageProxy(self.image_repo.get(image_id),
                                   self.context, self.property_rules)

    def list(self, *args, **kwargs):
        images = self.image_repo.list(*args, **kwargs)
        return [ProtectedImageProxy(image, self.context, self.property_rules)
                for image in images]


class ProtectedImageProxy(glance.domain.proxy.Image):

    def __init__(self, image, context, property_rules):
        self.image = image
        self.context = context
        self.property_rules = property_rules

        self.image.extra_properties = ExtraPropertiesProxy(
            self.context,
            self.image.extra_properties,
            self.property_rules)
        super(ProtectedImageProxy, self).__init__(self.image)


class ExtraPropertiesProxy(glance.domain.ExtraProperties):

    def __init__(self, context, extra_props, property_rules):
        self.context = context
        self.property_rules = property_rules
        extra_properties = {}
        for key in extra_props.keys():
            if self.property_rules.check_property_rules(key, 'read',
                                                        self.context):
                extra_properties[key] = extra_props[key]
        super(ExtraPropertiesProxy, self).__init__(extra_properties)

    def __getitem__(self, key):
        if self.property_rules.check_property_rules(key, 'read', self.context):
            return dict.__getitem__(self, key)
        else:
            raise KeyError

    def __setitem__(self, key, value):
        # NOTE(isethi): Exceptions are raised only for actions update, delete
        # and create, where the user proactively interacts with the properties.
        # A user cannot request to read a specific property, hence reads do
        # raise an exception
        try:
            if self.__getitem__(key) is not None:
                if self.property_rules.check_property_rules(key, 'update',
                                                            self.context):
                    return dict.__setitem__(self, key, value)
                else:
                    raise exception.ReservedProperty(property=key)
        except KeyError:
            if self.property_rules.check_property_rules(key, 'create',
                                                        self.context):
                return dict.__setitem__(self, key, value)
            else:
                raise exception.ReservedProperty(property=key)

    def __delitem__(self, key):
        if key not in super(ExtraPropertiesProxy, self).keys():
            raise KeyError

        if self.property_rules.check_property_rules(key, 'delete',
                                                    self.context):
            return dict.__delitem__(self, key)
        else:
            raise exception.ReservedProperty(property=key)
