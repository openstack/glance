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

import operator

import semantic_version
from sqlalchemy.orm.properties import CompositeProperty
from sqlalchemy import sql

from glance.common import exception
from glance import i18n

MAX_COMPONENT_LENGTH = pow(2, 16) - 1
MAX_NUMERIC_PRERELEASE_LENGTH = 6

_ = i18n._


class DBVersion(object):
    def __init__(self, components_long, prerelease, build):
        """
        Creates a DBVersion object out of 3 component fields. This initializer
        is supposed to be called from SQLAlchemy if 3 database columns are
        mapped to this composite field.

        :param components_long: a 64-bit long value, containing numeric
        components of the version
        :param prerelease: a prerelease label of the version, optionally
        preformatted with leading zeroes in numeric-only parts of the label
        :param build: a build label of the version
        """
        version_string = '%s.%s.%s' % _long_to_components(components_long)
        if prerelease:
            version_string += '-' + _strip_leading_zeroes_from_prerelease(
                prerelease)

        if build:
            version_string += '+' + build
        self.version = semantic_version.Version(version_string)

    def __repr__(self):
        return str(self.version)

    def __eq__(self, other):
        return (isinstance(other, DBVersion) and
                other.version == self.version)

    def __ne__(self, other):
        return (not isinstance(other, DBVersion)
                or self.version != other.version)

    def __composite_values__(self):
        long_version = _version_to_long(self.version)
        prerelease = _add_leading_zeroes_to_prerelease(self.version.prerelease)
        build = '.'.join(self.version.build) if self.version.build else None
        return long_version, prerelease, build


def parse(version_string):
    version = semantic_version.Version.coerce(version_string)
    return DBVersion(_version_to_long(version),
                     '.'.join(version.prerelease),
                     '.'.join(version.build))


def _check_limit(value):
    if value > MAX_COMPONENT_LENGTH:
        reason = _("Version component is too "
                   "large (%d max)") % MAX_COMPONENT_LENGTH
        raise exception.InvalidVersion(reason=reason)


def _version_to_long(version):
    """
    Converts the numeric part of the semver version into the 64-bit long value
    using the following logic:

    * major version is stored in first 16 bits of the value
    * minor version is stored in next 16 bits
    * patch version is stored in following 16 bits
    * next 2 bits are used to store the flag: if the version has pre-release
      label then these bits are 00, otherwise they are 11. Intermediate values
      of the flag (01 and 10) are reserved for future usage.
    * last 14 bits of the value are reserved fo future usage

    The numeric components of version are checked so their value do not exceed
    16 bits.

    :param version: a semantic_version.Version object
    """
    _check_limit(version.major)
    _check_limit(version.minor)
    _check_limit(version.patch)
    major = version.major << 48
    minor = version.minor << 32
    patch = version.patch << 16
    flag = 0 if version.prerelease else 2
    flag <<= 14
    return major | minor | patch | flag


def _long_to_components(value):
    major = value >> 48
    minor = (value - (major << 48)) >> 32
    patch = (value - (major << 48) - (minor << 32)) >> 16
    return str(major), str(minor), str(patch)


def _add_leading_zeroes_to_prerelease(label_tuple):
    if label_tuple is None:
        return None
    res = []
    for component in label_tuple:
        if component.isdigit():
            if len(component) > MAX_NUMERIC_PRERELEASE_LENGTH:
                reason = _("Prerelease numeric component is too large "
                           "(%d characters "
                           "max)") % MAX_NUMERIC_PRERELEASE_LENGTH
                raise exception.InvalidVersion(reason=reason)
            res.append(component.rjust(MAX_NUMERIC_PRERELEASE_LENGTH, '0'))
        else:
            res.append(component)
    return '.'.join(res)


def _strip_leading_zeroes_from_prerelease(string_value):
    res = []
    for component in string_value.split('.'):
        if component.isdigit():
            val = component.lstrip('0')
            if len(val) == 0:  # Corner case: when the component is just '0'
                val = '0'  # it will be stripped completely, so restore it
            res.append(val)
        else:
            res.append(component)
    return '.'.join(res)

strict_op_map = {
    operator.ge: operator.gt,
    operator.le: operator.lt
}


class VersionComparator(CompositeProperty.Comparator):
    def _get_comparison(self, values, op):
        columns = self.__clause_element__().clauses
        if op in strict_op_map:
            stricter_op = strict_op_map[op]
        else:
            stricter_op = op

        return sql.or_(stricter_op(columns[0], values[0]),
                       sql.and_(columns[0] == values[0],
                                op(columns[1], values[1])))

    def __gt__(self, other):
        return self._get_comparison(other.__composite_values__(), operator.gt)

    def __ge__(self, other):
        return self._get_comparison(other.__composite_values__(), operator.ge)

    def __lt__(self, other):
        return self._get_comparison(other.__composite_values__(), operator.lt)

    def __le__(self, other):
        return self._get_comparison(other.__composite_values__(), operator.le)
