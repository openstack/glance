# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2013 OpenStack Foundation
# Copyright 2013 Intel Corporation
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

"""Metadata setup commands."""

import threading

from oslo_config import cfg
from oslo_db import options as db_options
from stevedore import driver

from glance.db.sqlalchemy import api as db_api


_IMPL = None
_LOCK = threading.Lock()

db_options.set_defaults(cfg.CONF)


def get_backend():
    global _IMPL
    if _IMPL is None:
        with _LOCK:
            if _IMPL is None:
                _IMPL = driver.DriverManager(
                    "glance.database.metadata_backend",
                    cfg.CONF.database.backend).driver
    return _IMPL


def load_metadefs():
    """Read metadefinition files and insert data into the database"""
    return get_backend().db_load_metadefs(engine=db_api.get_engine(),
                                          metadata_path=None,
                                          merge=False,
                                          prefer_new=False,
                                          overwrite=False)


def unload_metadefs():
    """Unload metadefinitions from database"""
    return get_backend().db_unload_metadefs(engine=db_api.get_engine())


def export_metadefs():
    """Export metadefinitions from database to files"""
    return get_backend().db_export_metadefs(engine=db_api.get_engine(),
                                            metadata_path=None)
