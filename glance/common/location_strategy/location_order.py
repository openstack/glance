# Copyright 2014 IBM Corp.
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

"""Image location order based location strategy module"""


def get_strategy_name():
    """Return strategy module name."""
    return 'location_order'


def init():
    """Initialize strategy module."""
    pass


def get_ordered_locations(locations, **kwargs):
    """
    Order image location list.

    :param locations: The original image location list.
    :returns: The image location list with original natural order.
    """
    return locations
