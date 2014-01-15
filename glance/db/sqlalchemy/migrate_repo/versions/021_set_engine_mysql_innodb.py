# Copyright 2013 OpenStack Foundation
# All Rights Reserved.
# Copyright 2013 IBM Corp.
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

from sqlalchemy import MetaData

tables = ['image_locations']


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    if migrate_engine.name == "mysql":
        d = migrate_engine.execute("SHOW TABLE STATUS WHERE Engine!='InnoDB';")
        for row in d.fetchall():
            table_name = row[0]
            if table_name in tables:
                migrate_engine.execute("ALTER TABLE %s Engine=InnoDB" %
                                       table_name)


def downgrade(migrate_engine):
    pass
