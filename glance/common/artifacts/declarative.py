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

import copy
import re

import semantic_version
import six

from glance.common import exception as exc
from glance import i18n


_ = i18n._


class AttributeDefinition(object):
    """A base class for the attribute definitions which may be added to
    declaratively defined artifact types
    """

    ALLOWED_TYPES = (object,)

    def __init__(self,
                 display_name=None,
                 description=None,
                 readonly=False,
                 mutable=True,
                 required=False,
                 default=None):
        """Initializes attribute definition

        :param display_name: Display name of the attribute
        :param description: Description of the attribute
        :param readonly: Flag indicating if the value of attribute may not be
        changed once an artifact is created
        :param mutable: Flag indicating if the value of attribute may not be
        changed once an artifact is published
        :param required: Flag indicating if the value of attribute is required
        :param default: default value of the attribute
        """
        self.name = None
        self.display_name = display_name
        self.description = description
        self.readonly = readonly
        self.required = required
        self.mutable = mutable
        self.default = default
        self._add_validator('type',
                            lambda v: isinstance(v, self.ALLOWED_TYPES),
                            _("Not a valid value type"))
        self._validate_default()

    def _set_name(self, value):
        self.name = value
        if self.display_name is None:
            self.display_name = value

    def _add_validator(self, name, func, message):
        if not hasattr(self, '_validators'):
            self._validators = []
            self._validators_index = {}
        pair = (func, message)
        self._validators.append(pair)
        self._validators_index[name] = pair

    def _get_validator(self, name):
        return self._validators_index.get(name)

    def _remove_validator(self, name):
        pair = self._validators_index.pop(name, None)
        if pair is not None:
            self._validators.remove(pair)

    def _check_definition(self):
        self._validate_default()

    def _validate_default(self):
        if self.default:
            try:
                self.validate(self.default, 'default')
            except exc.InvalidArtifactPropertyValue:
                raise exc.InvalidArtifactTypePropertyDefinition(
                    _("Default value is invalid"))

    def get_value(self, obj):
        return getattr(obj, self.name)

    def set_value(self, obj, value):
        return setattr(obj, self.name, value)

    def validate(self, value, name=None):
        if value is None:
            if self.required:
                raise exc.InvalidArtifactPropertyValue(
                    name=name or self.name,
                    val=value,
                    msg=_('Value is required'))
            else:
                return

        first_error = next((msg for v_func, msg in self._validators
                            if not v_func(value)), None)
        if first_error:
            raise exc.InvalidArtifactPropertyValue(name=name or self.name,
                                                   val=value,
                                                   msg=first_error)


class ListAttributeDefinition(AttributeDefinition):
    """A base class for Attribute definitions having List-semantics

    Is inherited by Array, ArtifactReferenceList and BinaryObjectList
    """
    ALLOWED_TYPES = (list,)
    ALLOWED_ITEM_TYPES = (AttributeDefinition, )

    def _check_item_type(self, item):
        if not isinstance(item, self.ALLOWED_ITEM_TYPES):
            raise exc.InvalidArtifactTypePropertyDefinition(
                _('Invalid item type specification'))
        if item.default is not None:
            raise exc.InvalidArtifactTypePropertyDefinition(
                _('List definitions may hot have defaults'))

    def __init__(self, item_type, min_size=0, max_size=None, unique=False,
                 **kwargs):

        super(ListAttributeDefinition, self).__init__(**kwargs)
        if isinstance(item_type, list):
            for it in item_type:
                self._check_item_type(it)

            # we need to copy the item_type collection
            self.item_type = item_type[:]

            if min_size != 0:
                raise exc.InvalidArtifactTypePropertyDefinition(
                    _("Cannot specify 'min_size' explicitly")
                )

            if max_size is not None:
                raise exc.InvalidArtifactTypePropertyDefinition(
                    _("Cannot specify 'max_size' explicitly")
                )

            # setting max_size and min_size to the length of item_type,
            # as tuple-semantic assumes that the number of elements is set
            # by the type spec
            min_size = max_size = len(item_type)
        else:
            self._check_item_type(item_type)
            self.item_type = item_type

        if min_size:
            self.min_size(min_size)

        if max_size:
            self.max_size(max_size)

        if unique:
            self.unique()

    def min_size(self, value):
        self._min_size = value
        if value is not None:
            self._add_validator('min_size',
                                lambda v: len(v) >= self._min_size,
                                _('List size is less than minimum'))
        else:
            self._remove_validator('min_size')

    def max_size(self, value):
        self._max_size = value
        if value is not None:
            self._add_validator('max_size',
                                lambda v: len(v) <= self._max_size,
                                _('List size is greater than maximum'))
        else:
            self._remove_validator('max_size')

    def unique(self, value=True):
        self._unique = value
        if value:
            def _unique(items):
                seen = set()
                for item in items:
                    if item in seen:
                        return False
                    seen.add(item)
                return True
            self._add_validator('unique',
                                _unique, _('Items have to be unique'))
        else:
            self._remove_validator('unique')

    def _set_name(self, value):
        super(ListAttributeDefinition, self)._set_name(value)
        if isinstance(self.item_type, list):
            for i, item in enumerate(self.item_type):
                item._set_name("%s[%i]" % (value, i))
        else:
            self.item_type._set_name("%s[*]" % value)

    def validate(self, value, name=None):
        super(ListAttributeDefinition, self).validate(value, name)
        if value is not None:
            for i, item in enumerate(value):
                self._validate_item_at(item, i)

    def get_item_definition_at_index(self, index):
        if isinstance(self.item_type, list):
            if index < len(self.item_type):
                return self.item_type[index]
            else:
                return None
        return self.item_type

    def _validate_item_at(self, item, index):
        item_type = self.get_item_definition_at_index(index)
        # set name if none has been given to the list element at given index
        if (isinstance(self.item_type, list) and item_type and
                not item_type.name):
            item_type.name = "%s[%i]" % (self.name, index)
        if item_type:
            item_type.validate(item)


class DictAttributeDefinition(AttributeDefinition):
    """A base class for Attribute definitions having Map-semantics

    Is inherited by Dict
    """
    ALLOWED_TYPES = (dict,)
    ALLOWED_PROPERTY_TYPES = (AttributeDefinition,)

    def _check_prop(self, key, item):
        if (not isinstance(item, self.ALLOWED_PROPERTY_TYPES) or
                (key is not None and not isinstance(key, six.string_types))):
            raise exc.InvalidArtifactTypePropertyDefinition(
                _('Invalid dict property type specification'))

    @staticmethod
    def _validate_key(key):
        if not isinstance(key, six.string_types):
            raise exc.InvalidArtifactPropertyValue(
                _('Invalid dict property type'))

    def __init__(self, properties, min_properties=0, max_properties=0,
                 **kwargs):
        super(DictAttributeDefinition, self).__init__(**kwargs)
        if isinstance(properties, dict):
            for key, value in six.iteritems(properties):
                self._check_prop(key, value)
            # copy the properties dict
            self.properties = properties.copy()

            self._add_validator('keys',
                                lambda v: set(v.keys()) <= set(
                                    self.properties.keys()),
                                _('Dictionary contains unexpected key(s)'))
        else:
            self._check_prop(None, properties)
            self.properties = properties

        if min_properties:
            self.min_properties(min_properties)

        if max_properties:
            self.max_properties(max_properties)

    def min_properties(self, value):
        self._min_properties = value
        if value is not None:
            self._add_validator('min_properties',
                                lambda v: len(v) >= self._min_properties,
                                _('Dictionary size is less than '
                                  'minimum'))
        else:
            self._remove_validator('min_properties')

    def max_properties(self, value):
        self._max_properties = value
        if value is not None:
            self._add_validator('max_properties',
                                lambda v: len(v) <= self._max_properties,
                                _('Dictionary size is '
                                  'greater than maximum'))
        else:
            self._remove_validator('max_properties')

    def _set_name(self, value):
        super(DictAttributeDefinition, self)._set_name(value)
        if isinstance(self.properties, dict):
            for k, v in six.iteritems(self.properties):
                v._set_name(value)
        else:
            self.properties._set_name(value)

    def validate(self, value, name=None):
        super(DictAttributeDefinition, self).validate(value, name)
        if value is not None:
            for k, v in six.iteritems(value):
                self._validate_item_with_key(v, k)

    def _validate_item_with_key(self, value, key):
        self._validate_key(key)
        if isinstance(self.properties, dict):
            prop_def = self.properties.get(key)
            if prop_def is not None:
                name = "%s[%s]" % (prop_def.name, key)
                prop_def.validate(value, name=name)
        else:
            name = "%s[%s]" % (self.properties.name, key)
            self.properties.validate(value, name=name)

    def get_prop_definition_at_key(self, key):
        if isinstance(self.properties, dict):
            return self.properties.get(key)
        else:
            return self.properties


class PropertyDefinition(AttributeDefinition):
    """A base class for Attributes defining generic or type-specific metadata
    properties
    """
    DB_TYPE = None

    def __init__(self,
                 internal=False,
                 allowed_values=None,
                 validators=None,
                 **kwargs):
        """Defines a metadata property

        :param internal: a flag indicating that the property is internal, i.e.
        not returned to client
        :param allowed_values: specifies a list of values allowed for the
        property
        :param validators: specifies a list of custom validators for the
        property
        """
        super(PropertyDefinition, self).__init__(**kwargs)
        self.internal = internal
        self._allowed_values = None

        if validators is not None:
            try:
                for i, (f, m) in enumerate(validators):
                    self._add_validator("custom_%i" % i, f, m)
            except ValueError:
                raise exc.InvalidArtifactTypePropertyDefinition(
                    _("Custom validators list should contain tuples "
                      "'(function, message)'"))

        if allowed_values is not None:
            # copy the allowed_values, as this is going to create a
            # closure, and we need to make sure that external modification of
            # this list does not affect the created validator
            self.allowed_values(allowed_values)
        self._check_definition()

    def _validate_allowed_values(self):
        if self._allowed_values:
            try:
                for allowed_value in self._allowed_values:
                    self.validate(allowed_value, 'allowed_value')
            except exc.InvalidArtifactPropertyValue:
                raise exc.InvalidArtifactTypePropertyDefinition(
                    _("Allowed values %s are invalid under given validators") %
                    self._allowed_values)

    def allowed_values(self, values):
        self._allowed_values = values[:]
        if values is not None:
            self._add_validator('allowed', lambda v: v in self._allowed_values,
                                _("Is not allowed value"))
        else:
            self._remove_validator('allowed')
        self._check_definition()

    def _check_definition(self):
        self._validate_allowed_values()
        super(PropertyDefinition, self)._check_definition()


class RelationDefinition(AttributeDefinition):
    """A base class for Attributes defining cross-artifact relations"""
    def __init__(self, internal=False, **kwargs):
        self.internal = internal
        kwargs.setdefault('mutable', False)
        # if mutable=True has been passed -> raise an exception
        if kwargs['mutable'] is True:
            raise exc.InvalidArtifactTypePropertyDefinition(
                _("Dependency relations cannot be mutable"))
        super(RelationDefinition, self).__init__(**kwargs)


class BlobDefinition(AttributeDefinition):
    """A base class for Attributes defining binary objects"""
    pass


class ArtifactTypeMetaclass(type):
    """A metaclass to build  Artifact Types. Not intended to be used directly

    Use `get_declarative_base` to get the base class instead
    """
    def __init__(cls, class_name, bases, attributes):
        if '_declarative_artifact_type' not in cls.__dict__:
            _build_declarative_meta(cls)
        super(ArtifactTypeMetaclass, cls).__init__(class_name, bases,
                                                   attributes)


class ArtifactPropertyDescriptor(object):
    """A descriptor object for working with artifact attributes"""

    def __init__(self, prop, collection_wrapper_class=None):
        self.prop = prop
        self.collection_wrapper_class = collection_wrapper_class

    def __get__(self, instance, owner):
        if instance is None:
            # accessed via owner class
            return self.prop
        else:
            v = getattr(instance, '_' + self.prop.name, None)
            if v is None and self.prop.default is not None:
                v = copy.copy(self.prop.default)
                self.__set__(instance, v, ignore_mutability=True)
                return self.__get__(instance, owner)
            else:
                if v is not None and self.collection_wrapper_class:
                    if self.prop.readonly:
                        readonly = True
                    elif (not self.prop.mutable and
                          hasattr(instance, '__is_mutable__') and
                          not hasattr(instance,
                                      '__suspend_mutability_checks__')):

                        readonly = not instance.__is_mutable__()
                    else:
                        readonly = False
                    if readonly:
                        v = v.__make_immutable__()
                return v

    def __set__(self, instance, value, ignore_mutability=False):
        if instance:
            if self.prop.readonly:
                if hasattr(instance, '_' + self.prop.name):
                    raise exc.InvalidArtifactPropertyValue(
                        _('Attempt to set readonly property'))
            if not self.prop.mutable:
                if (hasattr(instance, '__is_mutable__') and
                        not hasattr(instance,
                                    '__suspend_mutability_checks__')):
                    mutable = instance.__is_mutable__() or ignore_mutability
                    if not mutable:
                        raise exc.InvalidArtifactPropertyValue(
                            _('Attempt to set value of immutable property'))
            if value is not None and self.collection_wrapper_class:
                value = self.collection_wrapper_class(value)
                value.property = self.prop
            self.prop.validate(value)
            setattr(instance, '_' + self.prop.name, value)


class ArtifactAttributes(object):
    """A container class storing description of Artifact Type attributes"""
    def __init__(self):
        self.properties = {}
        self.dependencies = {}
        self.blobs = {}
        self.all = {}

    @property
    def default_dependency(self):
        """Returns the default dependency relation for an artifact type"""
        if len(self.dependencies) == 1:
            return self.dependencies.values()[0]

    @property
    def default_blob(self):
        """Returns the default blob object for an artifact type"""
        if len(self.blobs) == 1:
            return self.blobs.values()[0]

    @property
    def default_properties_dict(self):
        """Returns a default properties dict for an artifact type"""
        dict_props = [v for v in self.properties.values() if
                      isinstance(v, DictAttributeDefinition)]
        if len(dict_props) == 1:
            return dict_props[0]

    @property
    def tags(self):
        """Returns tags property for an artifact type"""
        return self.properties.get('tags')

    def add(self, attribute):
        self.all[attribute.name] = attribute
        if isinstance(attribute, PropertyDefinition):
            self.properties[attribute.name] = attribute
        elif isinstance(attribute, BlobDefinition):
            self.blobs[attribute.name] = attribute
        elif isinstance(attribute, RelationDefinition):
            self.dependencies[attribute.name] = attribute


class ArtifactTypeMetadata(object):
    """A container to store the meta-information about an artifact type"""

    def __init__(self, type_name, type_display_name, type_version,
                 type_description, endpoint):
        """Initializes the Artifact Type metadata

        :param type_name: name of the artifact type
        :param type_display_name: display name of the artifact type
        :param type_version:  version of the artifact type
        :param type_description: description of the artifact type
        :param endpoint: REST API URI suffix to call the artifacts of this type
        """

        self.attributes = ArtifactAttributes()

        # These are going to be defined by third-party plugin
        # developers, so we need to do some validations on these values and
        # raise InvalidArtifactTypeDefinition if they are violated
        self.type_name = type_name
        self.type_display_name = type_display_name or type_name
        self.type_version = type_version or '1.0'
        self.type_description = type_description
        self.endpoint = endpoint or type_name.lower()

        self._validate_string(self.type_name, 'Type name', min_length=1,
                              max_length=255)
        self._validate_string(self.type_display_name, 'Type display name',
                              max_length=255)
        self._validate_string(self.type_description, 'Type description')
        self._validate_string(self.endpoint, 'endpoint', min_length=1)
        try:
            semantic_version.Version(self.type_version, partial=True)
        except ValueError:
            raise exc.InvalidArtifactTypeDefinition(
                message=_("Type version has to be a valid semver string"))

    @staticmethod
    def _validate_string(value, name, min_length=0, max_length=None,
                         pattern=None):
        if value is None:
            if min_length > 0:
                raise exc.InvalidArtifactTypeDefinition(
                    message=_("%(attribute)s is required"), attribute=name)
            else:
                return
        if not isinstance(value, six.string_types):
            raise exc.InvalidArtifactTypeDefinition(
                message=_("%(attribute)s have to be string"), attribute=name)
        if max_length and len(value) > max_length:
            raise exc.InvalidArtifactTypeDefinition(
                message=_("%(attribute)s may not be longer than %(length)i"),
                attribute=name, length=max_length)
        if min_length and len(value) < min_length:
            raise exc.InvalidArtifactTypeDefinition(
                message=_("%(attribute)s may not be shorter than %(length)i"),
                attribute=name, length=min_length)
        if pattern and not re.match(pattern, value):
            raise exc.InvalidArtifactTypeDefinition(
                message=_("%(attribute)s should match pattern %(pattern)s"),
                attribute=name, pattern=pattern.pattern)


def _build_declarative_meta(cls):
    attrs = dict(cls.__dict__)
    type_name = None
    type_display_name = None
    type_version = None
    type_description = None
    endpoint = None

    for base in cls.__mro__:
        for name, value in six.iteritems(vars(base)):
            if name == '__type_name__':
                if not type_name:
                    type_name = cls.__type_name__
            elif name == '__type_version__':
                if not type_version:
                    type_version = cls.__type_version__
            elif name == '__type_description__':
                if not type_description:
                    type_description = cls.__type_description__
            elif name == '__endpoint__':
                if not endpoint:
                    endpoint = cls.__endpoint__
            elif name == '__type_display_name__':
                if not type_display_name:
                    type_display_name = cls.__type_display_name__
            elif base is not cls and name not in attrs:
                if isinstance(value, AttributeDefinition):
                    attrs[name] = value
                elif isinstance(value, ArtifactPropertyDescriptor):
                    attrs[name] = value.prop

    meta = ArtifactTypeMetadata(type_name=type_name or cls.__name__,
                                type_display_name=type_display_name,
                                type_version=type_version,
                                type_description=type_description,
                                endpoint=endpoint)
    setattr(cls, 'metadata', meta)
    for k, v in attrs.items():
        if k == 'metadata':
            raise exc.InvalidArtifactTypePropertyDefinition(
                _("Cannot declare artifact property with reserved name "
                  "'metadata'"))
        if isinstance(v, AttributeDefinition):
            v._set_name(k)
            wrapper_class = None
            if isinstance(v, ListAttributeDefinition):
                wrapper_class = type("ValidatedList", (list,), {})
                _add_validation_to_list(wrapper_class)
            if isinstance(v, DictAttributeDefinition):
                wrapper_class = type("ValidatedDict", (dict,), {})
                _add_validation_to_dict(wrapper_class)
            prop_descr = ArtifactPropertyDescriptor(v, wrapper_class)
            setattr(cls, k, prop_descr)
            meta.attributes.add(v)


def _validating_method(method, klass):
    def wrapper(self, *args, **kwargs):
        instance_copy = klass(self)
        method(instance_copy, *args, **kwargs)
        self.property.validate(instance_copy)
        method(self, *args, **kwargs)

    return wrapper


def _immutable_method(method):
    def substitution(*args, **kwargs):
        raise exc.InvalidArtifactPropertyValue(
            _("Unable to modify collection in "
              "immutable or readonly property"))

    return substitution


def _add_immutable_wrappers(class_to_add, wrapped_methods):
    for method_name in wrapped_methods:
        method = getattr(class_to_add, method_name, None)
        if method:
            setattr(class_to_add, method_name, _immutable_method(method))


def _add_validation_wrappers(class_to_validate, base_class, validated_methods):
    for method_name in validated_methods:
        method = getattr(class_to_validate, method_name, None)
        if method:
            setattr(class_to_validate, method_name,
                    _validating_method(method, base_class))
    readonly_class = type("Readonly" + class_to_validate.__name__,
                          (class_to_validate,), {})
    _add_immutable_wrappers(readonly_class, validated_methods)

    def __make_immutable__(self):
        return readonly_class(self)

    class_to_validate.__make_immutable__ = __make_immutable__


def _add_validation_to_list(list_based_class):
    validated_methods = ['append', 'extend', 'insert', 'pop', 'remove',
                         'reverse', 'sort', '__setitem__', '__delitem__',
                         '__delslice__']
    _add_validation_wrappers(list_based_class, list, validated_methods)


def _add_validation_to_dict(dict_based_class):
    validated_methods = ['pop', 'popitem', 'setdefault', 'update',
                         '__delitem__', '__setitem__', 'clear']
    _add_validation_wrappers(dict_based_class, dict, validated_methods)


def _kwarg_init_constructor(self, **kwargs):
    self.__suspend_mutability_checks__ = True
    try:
        for k in kwargs:
            if not hasattr(type(self), k):
                raise exc.ArtifactInvalidProperty(prop=k)
            setattr(self, k, kwargs[k])
        self._validate_required(self.metadata.attributes.properties)
    finally:
        del self.__suspend_mutability_checks__


def _validate_required(self, attribute_dict):
    for k, v in six.iteritems(attribute_dict):
        if v.required and (not hasattr(self, k) or getattr(self, k) is None):
            raise exc.InvalidArtifactPropertyValue(name=k, val=None,
                                                   msg=_('Value is required'))


def _update(self, values):
    for k in values:
        if hasattr(type(self), k):
            setattr(self, k, values[k])
        else:
            raise exc.ArtifactInvalidProperty(prop=k)


def _pre_publish_validator(self, *args, **kwargs):
    self._validate_required(self.metadata.attributes.blobs)
    self._validate_required(self.metadata.attributes.dependencies)


_kwarg_init_constructor.__name__ = '__init__'
_pre_publish_validator.__name__ = '__pre_publish__'
_update.__name__ = 'update'


def get_declarative_base(name='base', base_class=object):
    """Returns a base class which should be inherited to construct Artifact
    Type object using the declarative syntax of attribute definition
    """
    bases = not isinstance(base_class, tuple) and (base_class,) or base_class
    class_dict = {'__init__': _kwarg_init_constructor,
                  '_validate_required': _validate_required,
                  '__pre_publish__': _pre_publish_validator,
                  '_declarative_artifact_type': True,
                  'update': _update}
    return ArtifactTypeMetaclass(name, bases, class_dict)
