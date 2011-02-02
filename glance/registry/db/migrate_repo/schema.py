# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import sqlalchemy.types
from sqlalchemy.schema import MetaData

String = lambda length: sqlalchemy.types.String(
    length=length, convert_unicode=False, assert_unicode=None,
    unicode_error=None, _warn_on_bytestring=False)


Text = lambda: sqlalchemy.types.Text(
    length=None, convert_unicode=False, assert_unicode=None,
    unicode_error=None, _warn_on_bytestring=False)


Boolean = lambda: sqlalchemy.types.Boolean(create_constraint=True, name=None)


DateTime = lambda: sqlalchemy.types.DateTime(timezone=False)


Integer = lambda: sqlalchemy.types.Integer()


meta = MetaData()
