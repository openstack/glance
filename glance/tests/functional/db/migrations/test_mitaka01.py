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

from oslo_db.sqlalchemy import test_fixtures
import sqlalchemy

from glance.tests.functional.db import test_migrations
import glance.tests.utils as test_utils


def get_indexes(table, engine):
    inspector = sqlalchemy.inspect(engine)
    return [idx['name'] for idx in inspector.get_indexes(table)]


class TestMitaka01Mixin(test_migrations.AlembicMigrationsMixin):

    def _pre_upgrade_mitaka01(self, engine):
        indexes = get_indexes('images', engine)
        self.assertNotIn('created_at_image_idx', indexes)
        self.assertNotIn('updated_at_image_idx', indexes)

    def _check_mitaka01(self, engine, data):
        indexes = get_indexes('images', engine)
        self.assertIn('created_at_image_idx', indexes)
        self.assertIn('updated_at_image_idx', indexes)


class TestMitaka01MySQL(
    TestMitaka01Mixin,
    test_fixtures.OpportunisticDBTestMixin,
    test_utils.BaseTestCase,
):
    FIXTURE = test_fixtures.MySQLOpportunisticFixture


class TestMitaka01PostgresSQL(
    TestMitaka01Mixin,
    test_fixtures.OpportunisticDBTestMixin,
    test_utils.BaseTestCase,
):
    FIXTURE = test_fixtures.PostgresqlOpportunisticFixture


class TestMitaka01Sqlite(
    TestMitaka01Mixin,
    test_fixtures.OpportunisticDBTestMixin,
    test_utils.BaseTestCase,
):
    pass
