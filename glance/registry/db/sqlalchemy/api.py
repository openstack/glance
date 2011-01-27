# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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
Implementation of SQLAlchemy backend
"""

import sys
from glance.common import db
from glance.common import exception
from glance.common import flags
from glance.common.db.sqlalchemy.session import get_session
from glance.registry.db.sqlalchemy import models
from sqlalchemy.orm import exc

#from sqlalchemy.orm import joinedload_all
# TODO(sirp): add back eager loading
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func

FLAGS = flags.FLAGS
