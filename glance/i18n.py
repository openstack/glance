# Copyright 2014 Red Hat, Inc.
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

from oslo_i18n import *  # noqa

_translators = TranslatorFactory(domain='glance')

# The primary translation function using the well-known name "_"
_ = _translators.primary


# i18n log translation functions are deprecated. While removing the invocations
# requires a lot of reviewing effort, we decide to make it as no-op functions.
def _LI(msg):
    return msg


def _LW(msg):
    return msg


def _LE(msg):
    return msg


def _LC(msg):
    return msg
