# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

from datetime import datetime

from oslo_utils import timeutils
from wsme import types as wsme_types


class WSMEModelTransformer(object):

    def to_dict(self):
        # Return the wsme_attributes names:values as a dict
        my_dict = {}
        for attribute in self._wsme_attributes:
            value = getattr(self, attribute.name)
            if value is not wsme_types.Unset:
                my_dict.update({attribute.name: value})
        return my_dict

    @classmethod
    def to_wsme_model(model, db_entity, self_link=None, schema=None):
        # Return the wsme_attributes names:values as a dict
        names = []
        for attribute in model._wsme_attributes:
            names.append(attribute.name)

        values = {}
        for name in names:
            value = getattr(db_entity, name, None)
            if value is not None:
                if type(value) == datetime:
                    iso_datetime_value = timeutils.isotime(value)
                    values.update({name: iso_datetime_value})
                else:
                    values.update({name: value})

        if schema:
            values['schema'] = schema

        model_object = model(**values)

        # 'self' kwarg is used in wsme.types.Base.__init__(self, ..) and
        # conflicts during initialization. self_link is a proxy field to self.
        if self_link:
            model_object.self = self_link

        return model_object

    @classmethod
    def get_mandatory_attrs(cls):
        return [attr.name for attr in cls._wsme_attributes if attr.mandatory]


def _get_value(obj):
    if obj is not wsme_types.Unset:
        return obj
    else:
        return None
