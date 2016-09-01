#    Copyright (c) 2016 Hewlett Packard Enterprise Software, LLC
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


from sqlalchemy import MetaData, Table


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    resource_types_table = Table('metadef_resource_types', meta, autoload=True)

    resource_types_table.update(values={'name': 'OS::Nova::Server'}).where(
        resource_types_table.c.name == 'OS::Nova::Instance').execute()
