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

from oslo_db.sqlalchemy import test_base
from oslo_db.sqlalchemy import utils as db_utils

from glance.tests.functional.db import test_migrations


class TestPikeExpand01Mixin(test_migrations.AlembicMigrationsMixin):

    artifacts_table_names = [
        'artifact_blob_locations',
        'artifact_properties',
        'artifact_blobs',
        'artifact_dependencies',
        'artifact_tags',
        'artifacts'
    ]

    def _get_revisions(self, config):
        return test_migrations.AlembicMigrationsMixin._get_revisions(
            self, config, head='pike_expand01')

    def _pre_upgrade_pike_expand01(self, engine):
        # verify presence of the artifacts tables
        for table_name in self.artifacts_table_names:
            table = db_utils.get_table(engine, table_name)
            self.assertIsNotNone(table)

    def _check_pike_expand01(self, engine, data):
        # should be no changes, so re-run pre-upgrade check
        self._pre_upgrade_pike_expand01(engine)


class TestPikeExpand01MySQL(TestPikeExpand01Mixin,
                            test_base.MySQLOpportunisticTestCase):
    pass
