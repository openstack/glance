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

import datetime
import numbers
import re

import semantic_version
import six

from glance.common.artifacts import declarative
import glance.common.exception as exc
from glance import i18n


_ = i18n._


class Text(declarative.PropertyDefinition):
    """A text metadata property of arbitrary length

    Maps to TEXT columns in database, does not support sorting or filtering
    """
    ALLOWED_TYPES = (six.string_types,)
    DB_TYPE = 'text'


# noinspection PyAttributeOutsideInit
class String(Text):
    """A string metadata property of limited length

    Maps to VARCHAR columns in database, supports filtering and sorting.
    May have constrains on length and regexp patterns.

    The maximum length is limited to 255 characters
    """

    DB_TYPE = 'string'

    def __init__(self, max_length=255, min_length=0, pattern=None, **kwargs):
        """Defines a String metadata property.

        :param max_length: maximum value length
        :param min_length: minimum value length
        :param pattern: regexp pattern to match
        """
        super(String, self).__init__(**kwargs)

        self.max_length(max_length)
        self.min_length(min_length)
        if pattern:
            self.pattern(pattern)
        # if default and/or allowed_values are specified (in base classes)
        # then we need to validate them against the newly added validators
        self._check_definition()

    def max_length(self, value):
        """Sets the maximum value length"""
        self._max_length = value
        if value is not None:
            if value > 255:
                raise exc.InvalidArtifactTypePropertyDefinition(
                    _('Max string length may not exceed 255 characters'))
            self._add_validator('max_length',
                                lambda v: len(v) <= self._max_length,
                                _('Length  is greater than maximum'))
        else:
            self._remove_validator('max_length')
        self._check_definition()

    def min_length(self, value):
        """Sets the minimum value length"""
        self._min_length = value
        if value is not None:
            if value < 0:
                raise exc.InvalidArtifactTypePropertyDefinition(
                    _('Min string length may not be negative'))

            self._add_validator('min_length',
                                lambda v: len(v) >= self._min_length,
                                _('Length is less than minimum'))
        else:
            self._remove_validator('min_length')
        self._check_definition()

    def pattern(self, value):
        """Sets the regexp pattern to match"""
        self._pattern = value
        if value is not None:
            self._add_validator('pattern',
                                lambda v: re.match(self._pattern,
                                                   v) is not None,
                                _('Does not match pattern'))
        else:
            self._remove_validator('pattern')
        self._check_definition()


class SemVerString(String):
    """A String metadata property matching semver pattern"""

    def __init__(self, **kwargs):
        def validate(value):
            try:
                semantic_version.Version(value, partial=True)
            except ValueError:
                return False
            return True

        super(SemVerString,
              self).__init__(validators=[(validate,
                                         "Invalid semver string")],
                             **kwargs)


# noinspection PyAttributeOutsideInit
class Integer(declarative.PropertyDefinition):
    """An Integer metadata property

    Maps to INT columns in Database, supports filtering and sorting.
    May have constraints on value
    """

    ALLOWED_TYPES = (six.integer_types,)
    DB_TYPE = 'int'

    def __init__(self, min_value=None, max_value=None, **kwargs):
        """Defines an Integer metadata property

        :param min_value: minimum allowed value
        :param max_value: maximum allowed value
        """
        super(Integer, self).__init__(**kwargs)
        if min_value is not None:
            self.min_value(min_value)

        if max_value is not None:
            self.max_value(max_value)

        # if default and/or allowed_values are specified (in base classes)
        # then we need to validate them against the newly added validators
        self._check_definition()

    def min_value(self, value):
        """Sets the minimum allowed value"""
        self._min_value = value
        if value is not None:
            self._add_validator('min_value',
                                lambda v: v >= self._min_value,
                                _('Value is less than minimum'))
        else:
            self._remove_validator('min_value')
        self._check_definition()

    def max_value(self, value):
        """Sets the maximum allowed value"""
        self._max_value = value
        if value is not None:
            self._add_validator('max_value',
                                lambda v: v <= self._max_value,
                                _('Value is greater than maximum'))
        else:
            self._remove_validator('max_value')
        self._check_definition()


# noinspection PyAttributeOutsideInit
class DateTime(declarative.PropertyDefinition):
    """A DateTime metadata property

    Maps to a DATETIME columns in database.
    Is not supported as Type Specific property, may be used only as Generic one

    May have constraints on value
    """
    ALLOWED_TYPES = (datetime.datetime,)
    DB_TYPE = 'datetime'

    def __init__(self, min_value=None, max_value=None, **kwargs):
        """Defines a DateTime metadata property

        :param min_value: minimum allowed value
        :param max_value: maximum allowed value
        """
        super(DateTime, self).__init__(**kwargs)
        if min_value is not None:
            self.min_value(min_value)

        if max_value is not None:
            self.max_value(max_value)

        # if default and/or allowed_values are specified (in base classes)
        # then we need to validate them against the newly added validators
        self._check_definition()

    def min_value(self, value):
        """Sets the minimum allowed value"""
        self._min_value = value
        if value is not None:
            self._add_validator('min_value',
                                lambda v: v >= self._min_value,
                                _('Value is less than minimum'))
        else:
            self._remove_validator('min_value')
        self._check_definition()

    def max_value(self, value):
        """Sets the maximum allowed value"""
        self._max_value = value
        if value is not None:
            self._add_validator('max_value',
                                lambda v: v <= self._max_value,
                                _('Value is greater than maximum'))
        else:
            self._remove_validator('max_value')
        self._check_definition()


# noinspection PyAttributeOutsideInit
class Numeric(declarative.PropertyDefinition):
    """A Numeric metadata property

    Maps to floating point number columns in Database, supports filtering and
    sorting. May have constraints on value
    """
    ALLOWED_TYPES = numbers.Number
    DB_TYPE = 'numeric'

    def __init__(self, min_value=None, max_value=None, **kwargs):
        """Defines a Numeric metadata property

        :param min_value: minimum allowed value
        :param max_value: maximum allowed value
        """
        super(Numeric, self).__init__(**kwargs)
        if min_value is not None:
            self.min_value(min_value)

        if max_value is not None:
            self.max_value(max_value)

        # if default and/or allowed_values are specified (in base classes)
        # then we need to validate them against the newly added validators
        self._check_definition()

    def min_value(self, value):
        """Sets the minimum allowed value"""
        self._min_value = value
        if value is not None:
            self._add_validator('min_value',
                                lambda v: v >= self._min_value,
                                _('Value is less than minimum'))
        else:
            self._remove_validator('min_value')
        self._check_definition()

    def max_value(self, value):
        """Sets the maximum allowed value"""
        self._max_value = value
        if value is not None:
            self._add_validator('max_value',
                                lambda v: v <= self._max_value,
                                _('Value is greater than maximum'))
        else:
            self._remove_validator('max_value')
        self._check_definition()


class Boolean(declarative.PropertyDefinition):
    """A Boolean metadata property

    Maps to Boolean columns in database. Supports filtering and sorting.
    """
    ALLOWED_TYPES = (bool,)
    DB_TYPE = 'bool'


class Array(declarative.ListAttributeDefinition,
            declarative.PropertyDefinition, list):
    """An array metadata property

    May contain elements of any other PropertyDefinition types except Dict and
    Array. Each elements maps to appropriate type of columns in database.
    Preserves order. Allows filtering based on "Array contains Value" semantics

    May specify constrains on types of elements, their amount and uniqueness.
    """
    ALLOWED_ITEM_TYPES = (declarative.PropertyDefinition,)

    def __init__(self, item_type=String(), min_size=0, max_size=None,
                 unique=False, extra_items=True, **kwargs):
        """Defines an Array metadata property

        :param item_type: defines the types of elements in Array. If set to an
        instance of PropertyDefinition then all the elements have to be of that
        type. If set to list of such instances, then the elements on the
        corresponding positions have to be of the appropriate type.
        :param min_size: minimum size of the Array
        :param max_size: maximum size of the Array
        :param unique: if set to true, all the elements in the Array have to be
        unique
        """
        if isinstance(item_type, Array):
            msg = _("Array property can't have item_type=Array")
            raise exc.InvalidArtifactTypePropertyDefinition(msg)
        declarative.ListAttributeDefinition.__init__(self,
                                                     item_type=item_type,
                                                     min_size=min_size,
                                                     max_size=max_size,
                                                     unique=unique)
        declarative.PropertyDefinition.__init__(self, **kwargs)


class Dict(declarative.DictAttributeDefinition,
           declarative.PropertyDefinition, dict):
    """A dictionary metadata property

    May contain elements of any other PropertyDefinition types except Dict.
    Each elements maps to appropriate type of columns in database. Allows
    filtering and sorting by values of each key except the ones mapping the
    Text fields.

    May specify constrains on types of elements and their amount.
    """
    ALLOWED_PROPERTY_TYPES = (declarative.PropertyDefinition,)

    def __init__(self, properties=String(), min_properties=0,
                 max_properties=None, **kwargs):
        """Defines a dictionary metadata property

        :param properties: defines the types of dictionary values. If set to an
        instance of PropertyDefinition then all the value have to be of that
        type. If set to a dictionary with string keys and values of
        PropertyDefinition type, then the elements mapped by the corresponding
        have have to be of the appropriate type.
        :param min_properties: minimum allowed amount of properties in the dict
        :param max_properties: maximum allowed amount of properties in the dict
        """
        declarative.DictAttributeDefinition.__init__(
            self,
            properties=properties,
            min_properties=min_properties,
            max_properties=max_properties)
        declarative.PropertyDefinition.__init__(self, **kwargs)


class ArtifactType(declarative.get_declarative_base()):  # noqa
    """A base class for all the Artifact Type definitions

    Defines the Generic metadata properties as attributes.
    """
    id = String(required=True, readonly=True)
    type_name = String(required=True, readonly=True)
    type_version = SemVerString(required=True, readonly=True)
    name = String(required=True, mutable=False)
    version = SemVerString(required=True, mutable=False)
    description = Text()
    tags = Array(unique=True, default=[])
    visibility = String(required=True,
                        allowed_values=["private", "public", "shared",
                                        "community"],
                        default="private")
    state = String(required=True, readonly=True, allowed_values=["creating",
                                                                 "active",
                                                                 "deactivated",
                                                                 "deleted"])
    owner = String(required=True, readonly=True)
    created_at = DateTime(required=True, readonly=True)
    updated_at = DateTime(required=True, readonly=True)
    published_at = DateTime(readonly=True)
    deleted_at = DateTime(readonly=True)

    def __init__(self, **kwargs):
        if "type_name" in kwargs:
            raise exc.InvalidArtifactPropertyValue(
                _("Unable to specify artifact type explicitly"))
        if "type_version" in kwargs:
            raise exc.InvalidArtifactPropertyValue(
                _("Unable to specify artifact type version explicitly"))
        super(ArtifactType,
              self).__init__(type_name=self.metadata.type_name,
                             type_version=self.metadata.type_version, **kwargs)

    def __eq__(self, other):
        if not isinstance(other, ArtifactType):
            return False
        return self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.id)

    def __is_mutable__(self):
        return self.state == "creating"


class ArtifactReference(declarative.RelationDefinition):
    """An artifact reference definition

    Allows to define constraints by the name and version of target artifact
    """
    ALLOWED_TYPES = ArtifactType

    def __init__(self, type_name=None, type_version=None, **kwargs):
        """Defines an artifact reference

        :param type_name: type name of the target artifact
        :param type_version: type version of the target artifact
        """
        super(ArtifactReference, self).__init__(**kwargs)
        if type_name is not None:
            if isinstance(type_name, list):
                type_names = list(type_name)
                if type_version is not None:
                    raise exc.InvalidArtifactTypePropertyDefinition(
                        _('Unable to specify version '
                          'if multiple types are possible'))
            else:
                type_names = [type_name]

            def validate_reference(artifact):
                if artifact.type_name not in type_names:
                    return False
                if (type_version is not None and
                   artifact.type_version != type_version):
                    return False
                return True

            self._add_validator('referenced_type',
                                validate_reference,
                                _("Invalid referenced type"))
        elif type_version is not None:
            raise exc.InvalidArtifactTypePropertyDefinition(
                _('Unable to specify version '
                  'if type is not specified'))
        self._check_definition()


class ArtifactReferenceList(declarative.ListAttributeDefinition,
                            declarative.RelationDefinition, list):
    """A list of Artifact References

    Allows to define a collection of references to other artifacts, each
    optionally constrained by type name and type version
    """
    ALLOWED_ITEM_TYPES = (ArtifactReference,)

    def __init__(self, references=ArtifactReference(), min_size=0,
                 max_size=None, **kwargs):
        if isinstance(references, list):
            raise exc.InvalidArtifactTypePropertyDefinition(
                _("Invalid reference list specification"))
        declarative.RelationDefinition.__init__(self, **kwargs)
        declarative.ListAttributeDefinition.__init__(self,
                                                     item_type=references,
                                                     min_size=min_size,
                                                     max_size=max_size,
                                                     unique=True,
                                                     default=[]
                                                     if min_size == 0 else
                                                     None)


class Blob(object):
    """A Binary object being part of the Artifact"""
    def __init__(self, size=0, locations=None, checksum=None, item_key=None):
        """Initializes a new Binary Object for an Artifact

        :param size: the size of Binary Data
        :param locations: a list of data locations in backing stores
        :param checksum: a checksum for the data
        """
        if locations is None:
            locations = []
        self.size = size
        self.checksum = checksum
        self.locations = locations
        self.item_key = item_key

    def to_dict(self):
        return {
            "size": self.size,
            "checksum": self.checksum,
        }


class BinaryObject(declarative.BlobDefinition, Blob):
    """A definition of BinaryObject binding

    Adds a BinaryObject to an Artifact Type, optionally constrained by file
    size and amount of locations
    """
    ALLOWED_TYPES = (Blob,)

    def __init__(self,
                 max_file_size=None,
                 min_file_size=None,
                 min_locations=None,
                 max_locations=None,
                 **kwargs):
        """Defines a binary object as part of Artifact Type
        :param max_file_size: maximum size of the associate Blob
        :param min_file_size: minimum size of the associated Blob
        :param min_locations: minimum number of locations in the associated
        Blob
        :param max_locations: maximum number of locations in the associated
        Blob
        """
        super(BinaryObject, self).__init__(default=None, readonly=False,
                                           mutable=False, **kwargs)
        self._max_file_size = max_file_size
        self._min_file_size = min_file_size
        self._min_locations = min_locations
        self._max_locations = max_locations

        self._add_validator('size_not_empty',
                            lambda v: v.size is not None,
                            _('Blob size is not set'))
        if max_file_size:
            self._add_validator('max_size',
                                lambda v: v.size <= self._max_file_size,
                                _("File too large"))
        if min_file_size:
            self._add_validator('min_size',
                                lambda v: v.size >= self._min_file_size,
                                _("File too small"))
        if min_locations:
            self._add_validator('min_locations',
                                lambda v: len(
                                    v.locations) >= self._min_locations,
                                _("Too few locations"))
        if max_locations:
            self._add_validator(
                'max_locations',
                lambda v: len(v.locations) <= self._max_locations,
                _("Too many locations"))


class BinaryObjectList(declarative.ListAttributeDefinition,
                       declarative.BlobDefinition, list):
    """A definition of binding to the list of BinaryObject

    Adds a list of BinaryObject's to an artifact type, optionally constrained
    by the number of objects in the list and their uniqueness

    """
    ALLOWED_ITEM_TYPES = (BinaryObject,)

    def __init__(self, objects=BinaryObject(), min_count=0, max_count=None,
                 **kwargs):
        declarative.BlobDefinition.__init__(self, **kwargs)
        declarative.ListAttributeDefinition.__init__(self,
                                                     item_type=objects,
                                                     min_size=min_count,
                                                     max_size=max_count,
                                                     unique=True)
        self.default = [] if min_count == 0 else None
