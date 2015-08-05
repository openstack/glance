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

import mock
import six

from glance.common.artifacts import declarative
import glance.common.artifacts.definitions as defs
from glance.common.artifacts import serialization
import glance.common.exception as exc
import glance.tests.utils as test_utils


BASE = declarative.get_declarative_base()


class TestDeclarativeProperties(test_utils.BaseTestCase):
    def test_artifact_type_properties(self):
        class SomeTypeWithNoExplicitName(BASE):
            some_attr = declarative.AttributeDefinition()

        class InheritedType(SomeTypeWithNoExplicitName):
            __type_version__ = '1.0'
            __type_name__ = 'ExplicitName'
            __type_description__ = 'Type description'
            __type_display_name__ = 'EXPLICIT_NAME'
            __endpoint__ = 'some_endpoint'

            some_attr = declarative.AttributeDefinition(display_name='NAME')

        base_type = SomeTypeWithNoExplicitName
        base_instance = SomeTypeWithNoExplicitName()
        self.assertIsNotNone(base_type.metadata)
        self.assertIsNotNone(base_instance.metadata)
        self.assertEqual(base_type.metadata, base_instance.metadata)
        self.assertEqual("SomeTypeWithNoExplicitName",
                         base_type.metadata.type_name)
        self.assertEqual("SomeTypeWithNoExplicitName",
                         base_type.metadata.type_display_name)
        self.assertEqual("1.0", base_type.metadata.type_version)
        self.assertIsNone(base_type.metadata.type_description)
        self.assertEqual('sometypewithnoexplicitname',
                         base_type.metadata.endpoint)

        self.assertIsNone(base_instance.some_attr)
        self.assertIsNotNone(base_type.some_attr)
        self.assertEqual(base_type.some_attr,
                         base_instance.metadata.attributes.all['some_attr'])
        self.assertEqual('some_attr', base_type.some_attr.name)
        self.assertEqual('some_attr', base_type.some_attr.display_name)
        self.assertIsNone(base_type.some_attr.description)

        derived_type = InheritedType
        derived_instance = InheritedType()

        self.assertIsNotNone(derived_type.metadata)
        self.assertIsNotNone(derived_instance.metadata)
        self.assertEqual(derived_type.metadata, derived_instance.metadata)
        self.assertEqual('ExplicitName', derived_type.metadata.type_name)
        self.assertEqual('EXPLICIT_NAME',
                         derived_type.metadata.type_display_name)
        self.assertEqual('1.0', derived_type.metadata.type_version)
        self.assertEqual('Type description',
                         derived_type.metadata.type_description)
        self.assertEqual('some_endpoint', derived_type.metadata.endpoint)
        self.assertIsNone(derived_instance.some_attr)
        self.assertIsNotNone(derived_type.some_attr)
        self.assertEqual(derived_type.some_attr,
                         derived_instance.metadata.attributes.all['some_attr'])
        self.assertEqual('some_attr', derived_type.some_attr.name)
        self.assertEqual('NAME', derived_type.some_attr.display_name)

    def test_wrong_type_definition(self):
        def declare_wrong_type_version():
            class WrongType(BASE):
                __type_version__ = 'abc'  # not a semver

            return WrongType

        def declare_wrong_type_name():
            class WrongType(BASE):
                __type_name__ = 'a' * 256  # too long

            return WrongType

        self.assertRaises(exc.InvalidArtifactTypeDefinition,
                          declare_wrong_type_version)
        self.assertRaises(exc.InvalidArtifactTypeDefinition,
                          declare_wrong_type_name)

    def test_base_declarative_attributes(self):
        class TestType(BASE):
            defaulted = declarative.PropertyDefinition(default=42)
            read_only = declarative.PropertyDefinition(readonly=True)
            required_attr = declarative.PropertyDefinition(required=True)

        e = self.assertRaises(exc.InvalidArtifactPropertyValue, TestType)
        self.assertEqual('required_attr', e.name)
        self.assertIsNone(e.value)
        tt = TestType(required_attr="universe")
        self.assertEqual('universe', tt.required_attr)
        self.assertEqual(42, tt.defaulted)
        self.assertIsNone(tt.read_only)

        tt = TestType(required_attr="universe", defaulted=0, read_only="Hello")
        self.assertEqual(0, tt.defaulted)
        self.assertEqual("Hello", tt.read_only)

        tt.defaulted = 5
        self.assertEqual(5, tt.defaulted)
        tt.required_attr = 'Foo'
        self.assertEqual('Foo', tt.required_attr)

        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'read_only', 'some_val')
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'required_attr', None)

        # no type checks in base AttributeDefinition
        o = object()
        tt.required_attr = o
        self.assertEqual(o, tt.required_attr)

    def test_generic_property(self):
        class TestType(BASE):
            simple_prop = declarative.PropertyDefinition()
            immutable_internal = declarative.PropertyDefinition(mutable=False,
                                                                internal=True)
            prop_with_allowed = declarative.PropertyDefinition(
                allowed_values=["Foo", True, 42])

        class DerivedType(TestType):
            prop_with_allowed = declarative.PropertyDefinition(
                allowed_values=["Foo", True, 42], required=True, default=42)

        tt = TestType()
        self.assertEqual(True,
                         tt.metadata.attributes.all['simple_prop'].mutable)
        self.assertEqual(False,
                         tt.metadata.attributes.all['simple_prop'].internal)
        self.assertEqual(False,
                         tt.metadata.attributes.all[
                             'immutable_internal'].mutable)
        self.assertEqual(True,
                         tt.metadata.attributes.all[
                             'immutable_internal'].internal)
        self.assertIsNone(tt.prop_with_allowed)
        tt = TestType(prop_with_allowed=42)
        self.assertEqual(42, tt.prop_with_allowed)
        tt = TestType(prop_with_allowed=True)
        self.assertEqual(True, tt.prop_with_allowed)
        tt = TestType(prop_with_allowed='Foo')
        self.assertEqual('Foo', tt.prop_with_allowed)

        tt.prop_with_allowed = 42
        self.assertEqual(42, tt.prop_with_allowed)
        tt.prop_with_allowed = 'Foo'
        self.assertEqual('Foo', tt.prop_with_allowed)
        tt.prop_with_allowed = True
        self.assertEqual(True, tt.prop_with_allowed)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr,
                          tt, 'prop_with_allowed', 'bar')
        # ensure that wrong assignment didn't change the value
        self.assertEqual(True, tt.prop_with_allowed)
        self.assertRaises(exc.InvalidArtifactPropertyValue, TestType,
                          prop_with_allowed=False)

        dt = DerivedType()
        self.assertEqual(42, dt.prop_with_allowed)

    def test_default_violates_allowed(self):
        def declare_wrong_type():
            class WrongType(BASE):
                prop = declarative.PropertyDefinition(
                    allowed_values=['foo', 'bar'],
                    default='baz')

            return WrongType

        self.assertRaises(exc.InvalidArtifactTypePropertyDefinition,
                          declare_wrong_type)

    def test_string_property(self):
        class TestType(BASE):
            simple = defs.String()
            with_length = defs.String(max_length=10, min_length=5)
            with_pattern = defs.String(pattern='^\\d+$', default='42')

        tt = TestType()
        tt.simple = 'foo'
        self.assertEqual('foo', tt.simple)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr,
                          tt, 'simple', 42)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr,
                          tt, 'simple', 'x' * 256)
        self.assertRaises(exc.InvalidArtifactPropertyValue, TestType,
                          simple='x' * 256)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr,
                          tt, 'with_length', 'x' * 11)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr,
                          tt, 'with_length', 'x' * 4)
        tt.simple = 'x' * 5
        self.assertEqual('x' * 5, tt.simple)
        tt.simple = 'x' * 10
        self.assertEqual('x' * 10, tt.simple)

        self.assertEqual("42", tt.with_pattern)
        tt.with_pattern = '0'
        self.assertEqual('0', tt.with_pattern)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'with_pattern', 'abc')
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'with_pattern', '.123.')

    def test_default_and_allowed_violates_string_constrains(self):
        def declare_wrong_default():
            class WrongType(BASE):
                prop = defs.String(min_length=4, default='foo')

            return WrongType

        def declare_wrong_allowed():
            class WrongType(BASE):
                prop = defs.String(min_length=4, allowed_values=['foo', 'bar'])

            return WrongType

        self.assertRaises(exc.InvalidArtifactTypePropertyDefinition,
                          declare_wrong_default)
        self.assertRaises(exc.InvalidArtifactTypePropertyDefinition,
                          declare_wrong_allowed)

    def test_integer_property(self):
        class TestType(BASE):
            simple = defs.Integer()
            constrained = defs.Integer(min_value=10, max_value=50)

        tt = TestType()
        self.assertIsNone(tt.simple)
        self.assertIsNone(tt.constrained)

        tt.simple = 0
        tt.constrained = 10
        self.assertEqual(0, tt.simple)
        self.assertEqual(10, tt.constrained)

        tt.constrained = 50
        self.assertEqual(50, tt.constrained)

        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'constrained', 1)
        self.assertEqual(50, tt.constrained)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'constrained', 51)
        self.assertEqual(50, tt.constrained)

        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'simple', '11')
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'simple', 10.5)

    def test_default_and_allowed_violates_int_constrains(self):
        def declare_wrong_default():
            class WrongType(BASE):
                prop = defs.Integer(min_value=4, default=1)

            return WrongType

        def declare_wrong_allowed():
            class WrongType(BASE):
                prop = defs.Integer(min_value=4, max_value=10,
                                    allowed_values=[1, 15])

            return WrongType

        self.assertRaises(exc.InvalidArtifactTypePropertyDefinition,
                          declare_wrong_default)
        self.assertRaises(exc.InvalidArtifactTypePropertyDefinition,
                          declare_wrong_allowed)

    def test_numeric_values(self):
        class TestType(BASE):
            simple = defs.Numeric()
            constrained = defs.Numeric(min_value=3.14, max_value=4.1)

        tt = TestType(simple=0.1, constrained=4)
        self.assertEqual(0.1, tt.simple)
        self.assertEqual(4.0, tt.constrained)

        tt.simple = 1
        self.assertEqual(1, tt.simple)
        tt.constrained = 3.14
        self.assertEqual(3.14, tt.constrained)
        tt.constrained = 4.1
        self.assertEqual(4.1, tt.constrained)

        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'simple', 'qwerty')
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'constrained', 3)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          'constrained', 5)

    def test_default_and_allowed_violates_numeric_constrains(self):
        def declare_wrong_default():
            class WrongType(BASE):
                prop = defs.Numeric(min_value=4.0, default=1.1)

            return WrongType

        def declare_wrong_allowed():
            class WrongType(BASE):
                prop = defs.Numeric(min_value=4.0, max_value=10.0,
                                    allowed_values=[1.0, 15.5])

            return WrongType

        self.assertRaises(exc.InvalidArtifactTypePropertyDefinition,
                          declare_wrong_default)
        self.assertRaises(exc.InvalidArtifactTypePropertyDefinition,
                          declare_wrong_allowed)

    def test_same_item_type_array(self):
        class TestType(BASE):
            simple = defs.Array()
            unique = defs.Array(unique=True)
            simple_with_allowed_values = defs.Array(
                defs.String(allowed_values=["Foo", "Bar"]))
            defaulted = defs.Array(defs.Boolean(), default=[True, False])
            constrained = defs.Array(item_type=defs.Numeric(min_value=0),
                                     min_size=3, max_size=5, unique=True)

        tt = TestType(simple=[])
        self.assertEqual([], tt.simple)
        tt.simple.append("Foo")
        self.assertEqual(["Foo"], tt.simple)
        tt.simple.append("Foo")
        self.assertEqual(["Foo", "Foo"], tt.simple)
        self.assertEqual(2, len(tt.simple))
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.simple.append,
                          42)
        tt.simple.pop(1)
        self.assertEqual(["Foo"], tt.simple)
        del tt.simple[0]
        self.assertEqual(0, len(tt.simple))

        tt.simple_with_allowed_values = ["Foo"]
        tt.simple_with_allowed_values.insert(0, "Bar")
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.simple_with_allowed_values.append, "Baz")

        self.assertEqual([True, False], tt.defaulted)
        tt.defaulted.pop()
        self.assertEqual([True], tt.defaulted)
        tt2 = TestType()
        self.assertEqual([True, False], tt2.defaulted)

        self.assertIsNone(tt.constrained)
        tt.constrained = [10, 5, 4]
        self.assertEqual([10, 5, 4], tt.constrained)
        tt.constrained[1] = 15
        self.assertEqual([10, 15, 4], tt.constrained)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.constrained.__setitem__, 1, -5)
        self.assertEqual([10, 15, 4], tt.constrained)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.constrained.remove, 15)
        self.assertEqual([10, 15, 4], tt.constrained)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.constrained.__delitem__, 1)
        self.assertEqual([10, 15, 4], tt.constrained)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.constrained.append, 15)
        self.assertEqual([10, 15, 4], tt.constrained)

        tt.unique = []
        tt.unique.append("foo")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.unique.append,
                          "foo")

    def test_tuple_style_array(self):
        class TestType(BASE):
            address = defs.Array(
                item_type=[defs.String(20), defs.Integer(min_value=1),
                           defs.Boolean()])

        tt = TestType(address=["Hope Street", 1234, True])
        self.assertEqual("Hope Street", tt.address[0])
        self.assertEqual(1234, tt.address[1])
        self.assertEqual(True, tt.address[2])

        # On Python 3, sort() fails because int (1) and string ("20") are not
        # comparable
        if six.PY2:
            self.assertRaises(exc.InvalidArtifactPropertyValue,
                              tt.address.sort)
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.address.pop, 0)
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.address.pop, 1)
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.address.pop)
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.address.append,
                          "Foo")

    def test_same_item_type_dict(self):
        class TestType(BASE):
            simple_props = defs.Dict()
            constrained_props = defs.Dict(
                properties=defs.Integer(min_value=1, allowed_values=[1, 2]),
                min_properties=2,
                max_properties=3)

        tt = TestType()
        self.assertIsNone(tt.simple_props)
        self.assertIsNone(tt.constrained_props)
        tt.simple_props = {}
        self.assertEqual({}, tt.simple_props)
        tt.simple_props["foo"] = "bar"
        self.assertEqual({"foo": "bar"}, tt.simple_props)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.simple_props.__setitem__, 42, "foo")
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.simple_props.setdefault, "bar", 42)

        tt.constrained_props = {"foo": 1, "bar": 2}
        self.assertEqual({"foo": 1, "bar": 2}, tt.constrained_props)
        tt.constrained_props["baz"] = 1
        self.assertEqual({"foo": 1, "bar": 2, "baz": 1}, tt.constrained_props)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.constrained_props.__setitem__, "foo", 3)
        self.assertEqual(1, tt.constrained_props["foo"])
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.constrained_props.__setitem__, "qux", 2)
        tt.constrained_props.pop("foo")
        self.assertEqual({"bar": 2, "baz": 1}, tt.constrained_props)
        tt.constrained_props['qux'] = 2
        self.assertEqual({"qux": 2, "bar": 2, "baz": 1}, tt.constrained_props)
        tt.constrained_props.popitem()
        dict_copy = tt.constrained_props.copy()
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.constrained_props.popitem)
        self.assertEqual(dict_copy, tt.constrained_props)

    def test_composite_dict(self):
        class TestType(BASE):
            props = defs.Dict(properties={"foo": defs.String(),
                                          "bar": defs.Boolean()})
            fixed = defs.Dict(properties={"name": defs.String(min_length=2),
                                          "age": defs.Integer(min_value=0,
                                                              max_value=99)})

        tt = TestType()
        tt.props = {"foo": "FOO", "bar": False}
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.props.__setitem__, "bar", 123)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.props.__setitem__, "extra", "value")
        tt.fixed = {"name": "Alex", "age": 42}
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.fixed.__setitem__, "age", 120)

    def test_immutables(self):
        class TestType(BASE):
            activated = defs.Boolean(required=True, default=False)
            name = defs.String(mutable=False)

            def __is_mutable__(self):
                return not self.activated

        tt = TestType()
        self.assertEqual(False, tt.activated)
        self.assertIsNone(tt.name)
        tt.name = "Foo"
        self.assertEqual("Foo", tt.name)
        tt.activated = True
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr,
                          tt, "name", "Bar")
        self.assertEqual("Foo", tt.name)
        tt.activated = False
        tt.name = "Bar"
        self.assertEqual("Bar", tt.name)

    def test_readonly_array_dict(self):
        class TestType(BASE):
            arr = defs.Array(readonly=True)
            dict = defs.Dict(readonly=True)

        tt = TestType(arr=["Foo", "Bar"], dict={"qux": "baz"})
        self.assertEqual(["Foo", "Bar"], tt.arr)
        self.assertEqual({"qux": "baz"}, tt.dict)
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.append,
                          "Baz")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.insert,
                          0, "Baz")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.__setitem__,
                          0, "Baz")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.remove,
                          "Foo")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.pop)
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.dict.pop,
                          "qux")
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.dict.__setitem__, "qux", "foo")

    def test_mutable_array_dict(self):
        class TestType(BASE):
            arr = defs.Array(mutable=False)
            dict = defs.Dict(mutable=False)
            activated = defs.Boolean()

            def __is_mutable__(self):
                return not self.activated

        tt = TestType()
        tt.arr = []
        tt.dict = {}
        tt.arr.append("Foo")
        tt.arr.insert(0, "Bar")
        tt.dict["baz"] = "qux"
        tt.activated = True
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.append,
                          "Baz")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.insert,
                          0, "Baz")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.__setitem__,
                          0, "Baz")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.remove,
                          "Foo")
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.pop)
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.dict.pop,
                          "qux")
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.dict.__setitem__, "qux", "foo")

    def test_readonly_as_write_once(self):
        class TestType(BASE):
            prop = defs.String(readonly=True)
            arr = defs.Array(readonly=True)

        tt = TestType()
        self.assertIsNone(tt.prop)
        tt.prop = "Foo"
        self.assertEqual("Foo", tt.prop)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt,
                          "prop", "bar")
        tt2 = TestType()
        self.assertIsNone(tt2.prop)
        tt2.prop = None
        self.assertIsNone(tt2.prop)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt2,
                          "prop", None)
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, tt2,
                          "prop", "foo")
        self.assertIsNone(tt.arr)
        tt.arr = ["foo", "bar"]
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.append,
                          'baz')
        self.assertIsNone(tt2.arr)
        tt2.arr = None
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.arr.append,
                          'baz')


class TestArtifactType(test_utils.BaseTestCase):
    def test_create_artifact(self):
        a = defs.ArtifactType(**get_artifact_fixture())
        self.assertIsNotNone(a)
        self.assertEqual("123", a.id)
        self.assertEqual("ArtifactType", a.type_name)
        self.assertEqual("1.0", a.type_version)
        self.assertEqual("11.2", a.version)
        self.assertEqual("Foo", a.name)
        self.assertEqual("private", a.visibility)
        self.assertEqual("creating", a.state)
        self.assertEqual("my_tenant", a.owner)
        self.assertEqual(a.created_at, a.updated_at)
        self.assertIsNone(a.description)
        self.assertIsNone(a.published_at)
        self.assertIsNone(a.deleted_at)

        self.assertIsNone(a.description)

        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a, "id",
                          "foo")
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a,
                          "state", "active")
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a,
                          "owner", "some other")
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a,
                          "created_at", datetime.datetime.now())
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a,
                          "deleted_at", datetime.datetime.now())
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a,
                          "updated_at", datetime.datetime.now())
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a,
                          "published_at", datetime.datetime.now())
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, a,
                          "visibility", "wrong")

    def test_dependency_prop(self):
        class DerivedType(defs.ArtifactType):
            depends_on_any = defs.ArtifactReference()
            depends_on_self = defs.ArtifactReference(type_name='DerivedType')
            depends_on_self_version = defs.ArtifactReference(
                type_name='DerivedType',
                type_version='1.0')

        class DerivedTypeV11(DerivedType):
            __type_name__ = 'DerivedType'
            __type_version__ = '1.1'
            depends_on_self_version = defs.ArtifactReference(
                type_name='DerivedType',
                type_version='1.1')

        d1 = DerivedType(**get_artifact_fixture())
        d2 = DerivedTypeV11(**get_artifact_fixture())
        a = defs.ArtifactType(**get_artifact_fixture())
        d1.depends_on_any = a
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, d1,
                          'depends_on_self', a)
        d1.depends_on_self = d2
        d2.depends_on_self = d1
        d1.depends_on_self_version = d1
        d2.depends_on_self_version = d2
        self.assertRaises(exc.InvalidArtifactPropertyValue, setattr, d1,
                          'depends_on_self_version', d2)

    def test_dependency_list(self):
        class FooType(defs.ArtifactType):
            pass

        class BarType(defs.ArtifactType):
            pass

        class TestType(defs.ArtifactType):
            depends_on = defs.ArtifactReferenceList()
            depends_on_self_or_foo = defs.ArtifactReferenceList(
                references=defs.ArtifactReference(['FooType', 'TestType']))

        a = defs.ArtifactType(**get_artifact_fixture(id="1"))
        a_copy = defs.ArtifactType(**get_artifact_fixture(id="1"))
        b = defs.ArtifactType(**get_artifact_fixture(id="2"))

        tt = TestType(**get_artifact_fixture(id="3"))
        foo = FooType(**get_artifact_fixture(id='4'))
        bar = BarType(**get_artifact_fixture(id='4'))

        tt.depends_on.append(a)
        tt.depends_on.append(b)
        self.assertEqual([a, b], tt.depends_on)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.depends_on.append, a)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.depends_on.append, a_copy)

        tt.depends_on_self_or_foo.append(tt)
        tt.depends_on_self_or_foo.append(foo)
        self.assertRaises(exc.InvalidArtifactPropertyValue,
                          tt.depends_on_self_or_foo.append, bar)
        self.assertEqual([tt, foo], tt.depends_on_self_or_foo)

    def test_blob(self):
        class TestType(defs.ArtifactType):
            image_file = defs.BinaryObject(max_file_size=201054,
                                           min_locations=1,
                                           max_locations=5)
            screen_shots = defs.BinaryObjectList(
                objects=defs.BinaryObject(min_file_size=100), min_count=1)

        tt = TestType(**get_artifact_fixture())
        blob = defs.Blob()
        blob.size = 1024
        blob.locations.append("file://some.file.path")
        tt.image_file = blob

        self.assertEqual(1024, tt.image_file.size)
        self.assertEqual(["file://some.file.path"], tt.image_file.locations)

    def test_pre_publish_blob_validation(self):
        class TestType(defs.ArtifactType):
            required_blob = defs.BinaryObject(required=True)
            optional_blob = defs.BinaryObject()

        tt = TestType(**get_artifact_fixture())
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.__pre_publish__)
        tt.required_blob = defs.Blob(size=0)
        tt.__pre_publish__()

    def test_pre_publish_dependency_validation(self):
        class TestType(defs.ArtifactType):
            required_dependency = defs.ArtifactReference(required=True)
            optional_dependency = defs.ArtifactReference()

        tt = TestType(**get_artifact_fixture())
        self.assertRaises(exc.InvalidArtifactPropertyValue, tt.__pre_publish__)
        tt.required_dependency = defs.ArtifactType(**get_artifact_fixture())
        tt.__pre_publish__()

    def test_default_value_of_immutable_field_in_active_state(self):
        class TestType(defs.ArtifactType):
            foo = defs.String(default='Bar', mutable=False)
        tt = TestType(**get_artifact_fixture(state='active'))
        self.assertEqual('Bar', tt.foo)


class SerTestType(defs.ArtifactType):
    some_string = defs.String()
    some_text = defs.Text()
    some_version = defs.SemVerString()
    some_int = defs.Integer()
    some_numeric = defs.Numeric()
    some_bool = defs.Boolean()
    some_array = defs.Array()
    another_array = defs.Array(
        item_type=[defs.Integer(), defs.Numeric(), defs.Boolean()])
    some_dict = defs.Dict()
    another_dict = defs.Dict(
        properties={'foo': defs.Integer(), 'bar': defs.Boolean()})
    some_ref = defs.ArtifactReference()
    some_ref_list = defs.ArtifactReferenceList()
    some_blob = defs.BinaryObject()
    some_blob_list = defs.BinaryObjectList()


class TestSerialization(test_utils.BaseTestCase):
    def test_serialization_to_db(self):
        ref1 = defs.ArtifactType(**get_artifact_fixture(id="1"))
        ref2 = defs.ArtifactType(**get_artifact_fixture(id="2"))
        ref3 = defs.ArtifactType(**get_artifact_fixture(id="3"))

        blob1 = defs.Blob(size=100, locations=['http://example.com/blob1'],
                          item_key='some_key', checksum='abc')
        blob2 = defs.Blob(size=200, locations=['http://example.com/blob2'],
                          item_key='another_key', checksum='fff')
        blob3 = defs.Blob(size=300, locations=['http://example.com/blob3'],
                          item_key='third_key', checksum='123')

        fixture = get_artifact_fixture()
        tt = SerTestType(**fixture)
        tt.some_string = 'bar'
        tt.some_text = 'bazz'
        tt.some_version = '11.22.33-beta'
        tt.some_int = 50
        tt.some_numeric = 10.341
        tt.some_bool = True
        tt.some_array = ['q', 'w', 'e', 'r', 't', 'y']
        tt.another_array = [1, 1.2, False]
        tt.some_dict = {'foobar': "FOOBAR", 'baz': "QUX"}
        tt.another_dict = {'foo': 1, 'bar': True}
        tt.some_ref = ref1
        tt.some_ref_list = [ref2, ref3]
        tt.some_blob = blob1
        tt.some_blob_list = [blob2, blob3]

        results = serialization.serialize_for_db(tt)
        expected = fixture
        expected['type_name'] = 'SerTestType'
        expected['type_version'] = '1.0'
        expected['properties'] = {
            'some_string': {
                'type': 'string',
                'value': 'bar'
            },
            'some_text': {
                'type': 'text',
                'value': 'bazz'
            },
            'some_version': {
                'type': 'string',
                'value': '11.22.33-beta'
            },
            'some_int': {
                'type': 'int',
                'value': 50
            },
            'some_numeric': {
                'type': 'numeric',
                'value': 10.341
            },
            'some_bool': {
                'type': 'bool',
                'value': True
            },
            'some_array': {
                'type': 'array',
                'value': [
                    {
                        'type': 'string',
                        'value': 'q'
                    },
                    {
                        'type': 'string',
                        'value': 'w'
                    },
                    {
                        'type': 'string',
                        'value': 'e'
                    },
                    {
                        'type': 'string',
                        'value': 'r'
                    },
                    {
                        'type': 'string',
                        'value': 't'
                    },
                    {
                        'type': 'string',
                        'value': 'y'
                    }
                ]
            },
            'another_array': {
                'type': 'array',
                'value': [
                    {
                        'type': 'int',
                        'value': 1
                    },
                    {
                        'type': 'numeric',
                        'value': 1.2
                    },
                    {
                        'type': 'bool',
                        'value': False
                    }
                ]
            },
            'some_dict.foobar': {
                'type': 'string',
                'value': 'FOOBAR'
            },
            'some_dict.baz': {
                'type': 'string',
                'value': 'QUX'
            },
            'another_dict.foo': {
                'type': 'int',
                'value': 1
            },
            'another_dict.bar': {
                'type': 'bool',
                'value': True
            }
        }
        expected['dependencies'] = {
            'some_ref': ['1'],
            'some_ref_list': ['2', '3']
        }
        expected['blobs'] = {
            'some_blob': [
                {
                    'size': 100,
                    'checksum': 'abc',
                    'item_key': 'some_key',
                    'locations': ['http://example.com/blob1']
                }],
            'some_blob_list': [
                {
                    'size': 200,
                    'checksum': 'fff',
                    'item_key': 'another_key',
                    'locations': ['http://example.com/blob2']
                },
                {
                    'size': 300,
                    'checksum': '123',
                    'item_key': 'third_key',
                    'locations': ['http://example.com/blob3']
                }
            ]
        }

        self.assertEqual(expected, results)

    def test_deserialize_from_db(self):
        ts = datetime.datetime.now()
        db_dict = {
            "type_name": 'SerTestType',
            "type_version": '1.0',
            "id": "123",
            "version": "11.2",
            "description": None,
            "name": "Foo",
            "visibility": "private",
            "state": "creating",
            "owner": "my_tenant",
            "created_at": ts,
            "updated_at": ts,
            "deleted_at": None,
            "published_at": None,
            "tags": ["test", "fixture"],
            "properties": {
                'some_string': {
                    'type': 'string',
                    'value': 'bar'
                },
                'some_text': {
                    'type': 'text',
                    'value': 'bazz'
                },
                'some_version': {
                    'type': 'string',
                    'value': '11.22.33-beta'
                },
                'some_int': {
                    'type': 'int',
                    'value': 50
                },
                'some_numeric': {
                    'type': 'numeric',
                    'value': 10.341
                },
                'some_bool': {
                    'type': 'bool',
                    'value': True
                },
                'some_array': {
                    'type': 'array',
                    'value': [
                        {
                            'type': 'string',
                            'value': 'q'
                        },
                        {
                            'type': 'string',
                            'value': 'w'
                        },
                        {
                            'type': 'string',
                            'value': 'e'
                        },
                        {
                            'type': 'string',
                            'value': 'r'
                        },
                        {
                            'type': 'string',
                            'value': 't'
                        },
                        {
                            'type': 'string',
                            'value': 'y'
                        }
                    ]
                },
                'another_array': {
                    'type': 'array',
                    'value': [
                        {
                            'type': 'int',
                            'value': 1
                        },
                        {
                            'type': 'numeric',
                            'value': 1.2
                        },
                        {
                            'type': 'bool',
                            'value': False
                        }
                    ]
                },
                'some_dict.foobar': {
                    'type': 'string',
                    'value': 'FOOBAR'
                },
                'some_dict.baz': {
                    'type': 'string',
                    'value': 'QUX'
                },
                'another_dict.foo': {
                    'type': 'int',
                    'value': 1
                },
                'another_dict.bar': {
                    'type': 'bool',
                    'value': True
                }
            },
            'blobs': {
                'some_blob': [
                    {
                        'size': 100,
                        'checksum': 'abc',
                        'item_key': 'some_key',
                        'locations': ['http://example.com/blob1']
                    }],
                'some_blob_list': [
                    {
                        'size': 200,
                        'checksum': 'fff',
                        'item_key': 'another_key',
                        'locations': ['http://example.com/blob2']
                    },
                    {
                        'size': 300,
                        'checksum': '123',
                        'item_key': 'third_key',
                        'locations': ['http://example.com/blob3']
                    }
                ]
            },
            'dependencies': {
                'some_ref': [
                    {
                        "type_name": 'ArtifactType',
                        "type_version": '1.0',
                        "id": "1",
                        "version": "11.2",
                        "description": None,
                        "name": "Foo",
                        "visibility": "private",
                        "state": "creating",
                        "owner": "my_tenant",
                        "created_at": ts,
                        "updated_at": ts,
                        "deleted_at": None,
                        "published_at": None,
                        "tags": ["test", "fixture"],
                        "properties": {},
                        "blobs": {},
                        "dependencies": {}
                    }
                ],
                'some_ref_list': [
                    {
                        "type_name": 'ArtifactType',
                        "type_version": '1.0',
                        "id": "2",
                        "version": "11.2",
                        "description": None,
                        "name": "Foo",
                        "visibility": "private",
                        "state": "creating",
                        "owner": "my_tenant",
                        "created_at": ts,
                        "updated_at": ts,
                        "deleted_at": None,
                        "published_at": None,
                        "tags": ["test", "fixture"],
                        "properties": {},
                        "blobs": {},
                        "dependencies": {}
                    },
                    {
                        "type_name": 'ArtifactType',
                        "type_version": '1.0',
                        "id": "3",
                        "version": "11.2",
                        "description": None,
                        "name": "Foo",
                        "visibility": "private",
                        "state": "creating",
                        "owner": "my_tenant",
                        "created_at": ts,
                        "updated_at": ts,
                        "deleted_at": None,
                        "published_at": None,
                        "tags": ["test", "fixture"],
                        "properties": {},
                        "blobs": {},
                        "dependencies": {}
                    }
                ]
            }
        }
        plugins_dict = {'SerTestType': [SerTestType],
                        'ArtifactType': [defs.ArtifactType]}

        def _retrieve_plugin(name, version):
            return next((p for p in plugins_dict.get(name, [])
                        if version and p.version == version),
                        plugins_dict.get(name, [None])[0])
        plugins = mock.Mock()
        plugins.get_class_by_typename = _retrieve_plugin
        art = serialization.deserialize_from_db(db_dict, plugins)
        self.assertEqual('123', art.id)
        self.assertEqual('11.2', art.version)
        self.assertIsNone(art.description)
        self.assertEqual('Foo', art.name)
        self.assertEqual('private', art.visibility)
        self.assertEqual('private', art.visibility)


def get_artifact_fixture(**kwargs):
    ts = datetime.datetime.now()
    fixture = {
        "id": "123",
        "version": "11.2",
        "description": None,
        "name": "Foo",
        "visibility": "private",
        "state": "creating",
        "owner": "my_tenant",
        "created_at": ts,
        "updated_at": ts,
        "deleted_at": None,
        "published_at": None,
        "tags": ["test", "fixture"]
    }
    fixture.update(kwargs)
    return fixture
