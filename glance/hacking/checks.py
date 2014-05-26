# Copyright (c) 2014 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


def no_translate_debug_logs(logical_line, filename):
    dirs = [
        "glance/api",
        "glance/cmd",
        "glance/common",
        "glance/db",
        "glance/domain",
        "glance/image_cache",
        "glance/quota",
        "glance/registry",
        "glance/store",
        "glance/tests",
    ]

    if max([name in filename for name in dirs]):
        if logical_line.startswith("LOG.debug(_("):
            yield(0, "N319: Don't translate debug level logs")


def factory(register):
    register(no_translate_debug_logs)
