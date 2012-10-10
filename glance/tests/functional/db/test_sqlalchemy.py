# Copyright 2012 OpenStack, LLC
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


import glance.db.sqlalchemy.api
from glance.db.sqlalchemy import models as db_models
import glance.tests.functional.db as db_tests


def get_db(config):
    config(sql_connection='sqlite://', verbose=False, debug=False)
    db_api = glance.db.sqlalchemy.api
    db_api.configure_db()
    return db_api


def reset_db(db_api):
    db_models.unregister_models(db_api._ENGINE)
    db_models.register_models(db_api._ENGINE)


def setUpModule():
    """Stub in get_db and reset_db for testing the sqlalchemy db api."""
    db_tests.load(get_db, reset_db)


def tearDownModule():
    """Reset get_db and reset_db for cleanliness."""
    db_tests.reset()


#NOTE(markwash): Pull in all the base test cases
from glance.tests.functional.db.base import *
