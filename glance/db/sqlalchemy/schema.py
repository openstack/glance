# Copyright 2011 OpenStack Foundation
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

"""
Various conveniences used for migration scripts
"""

from oslo_log import log as logging
import sqlalchemy.types


LOG = logging.getLogger(__name__)


def String(length):
    return sqlalchemy.types.String(length=length)


def Text():
    return sqlalchemy.types.Text(length=None)


def Boolean():
    return sqlalchemy.types.Boolean(create_constraint=True, name=None)


def DateTime():
    return sqlalchemy.types.DateTime(timezone=False)


def Integer():
    return sqlalchemy.types.Integer()


def BigInteger():
    return sqlalchemy.types.BigInteger()


def PickleType():
    return sqlalchemy.types.PickleType()


def Numeric():
    return sqlalchemy.types.Numeric()
