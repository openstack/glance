# Copyright 2023 OpenStack Foundation
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
Common code which will be used in SQLite and centralzed_db driver until SQLite
driver is removed from glance.
"""
from contextlib import contextmanager
import sqlite3

from eventlet import sleep
from eventlet import timeout
from oslo_log import log as logging

from glance.i18n import _LE


LOG = logging.getLogger(__name__)

DEFAULT_SQL_CALL_TIMEOUT = 2


def dict_factory(cur, row):
    return {col[0]: row[idx] for idx, col in enumerate(cur.description)}


class SqliteConnection(sqlite3.Connection):

    """
    SQLite DB Connection handler that plays well with eventlet,
    slightly modified from Swift's similar code.
    """

    def __init__(self, *args, **kwargs):
        self.timeout_seconds = kwargs.get('timeout', DEFAULT_SQL_CALL_TIMEOUT)
        kwargs['timeout'] = 0
        sqlite3.Connection.__init__(self, *args, **kwargs)

    def _timeout(self, call):
        with timeout.Timeout(self.timeout_seconds):
            while True:
                try:
                    return call()
                except sqlite3.OperationalError as e:
                    if 'locked' not in str(e):
                        raise
                sleep(0.05)

    def execute(self, *args, **kwargs):
        return self._timeout(lambda: sqlite3.Connection.execute(
            self, *args, **kwargs))

    def commit(self):
        return self._timeout(lambda: sqlite3.Connection.commit(self))


@contextmanager
def get_db(db_path):
    """
    Returns a context manager that produces a database connection that
    self-closes and calls rollback if an error occurs while using the
    database connection
    """
    conn = sqlite3.connect(db_path, check_same_thread=False,
                           factory=SqliteConnection)
    conn.row_factory = sqlite3.Row
    conn.text_factory = str
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.execute('PRAGMA count_changes = OFF')
    conn.execute('PRAGMA temp_store = MEMORY')
    try:
        yield conn
    except sqlite3.DatabaseError as e:
        msg = _LE("Error executing SQLite call. Got error: %s") % e
        LOG.error(msg)
        conn.rollback()
    finally:
        conn.close()
