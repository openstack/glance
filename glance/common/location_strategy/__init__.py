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

import copy

from oslo_config import cfg
from oslo_log import log as logging
import stevedore

from glance.i18n import _, _LE

location_strategy_opts = [
    cfg.StrOpt('location_strategy',
               default='location_order',
               choices=('location_order', 'store_type'),
               help=_("""
Strategy to determine the preference order of image locations.

This configuration option indicates the strategy to determine
the order in which an image's locations must be accessed to
serve the image's data. Glance then retrieves the image data
from the first responsive active location it finds in this list.

This option takes one of two possible values ``location_order``
and ``store_type``. The default value is ``location_order``,
which suggests that image data be served by using locations in
the order they are stored in Glance. The ``store_type`` value
sets the image location preference based on the order in which
the storage backends are listed as a comma separated list for
the configuration option ``store_type_preference``.

Possible values:
    * location_order
    * store_type

Related options:
    * store_type_preference

""")),
]

CONF = cfg.CONF
CONF.register_opts(location_strategy_opts)

LOG = logging.getLogger(__name__)


def _load_strategies():
    """Load all strategy modules."""
    modules = {}
    namespace = "glance.common.image_location_strategy.modules"
    ex = stevedore.extension.ExtensionManager(namespace)
    for module_name in ex.names():
        try:
            mgr = stevedore.driver.DriverManager(
                namespace=namespace,
                name=module_name,
                invoke_on_load=False)

            # Obtain module name
            strategy_name = str(mgr.driver.get_strategy_name())
            if strategy_name in modules:
                msg = (_('%(strategy)s is registered as a module twice. '
                         '%(module)s is not being used.') %
                       {'strategy': strategy_name, 'module': module_name})
                LOG.warn(msg)
            else:
                # Initialize strategy module
                mgr.driver.init()
                modules[strategy_name] = mgr.driver
        except Exception as e:
            LOG.error(_LE("Failed to load location strategy module "
                          "%(module)s: %(e)s"), {'module': module_name,
                                                 'e': e})
    return modules


_available_strategies = _load_strategies()


# TODO(kadachi): Not used but don't remove this until glance_store
#                development/migration stage.
def verify_location_strategy(conf=None, strategies=_available_strategies):
    """Validate user configured 'location_strategy' option value."""
    if not conf:
        conf = CONF.location_strategy
    if conf not in strategies:
        msg = (_('Invalid location_strategy option: %(name)s. '
                 'The valid strategy option(s) is(are): %(strategies)s') %
               {'name': conf, 'strategies': ", ".join(strategies.keys())})
        LOG.error(msg)
        raise RuntimeError(msg)


def get_ordered_locations(locations, **kwargs):
    """
    Order image location list by configured strategy.

    :param locations: The original image location list.
    :param kwargs: Strategy-specific arguments for under layer strategy module.
    :returns: The image location list with strategy-specific order.
    """
    if not locations:
        return []
    strategy_module = _available_strategies[CONF.location_strategy]
    return strategy_module.get_ordered_locations(copy.deepcopy(locations),
                                                 **kwargs)


def choose_best_location(locations, **kwargs):
    """
    Choose best location from image location list by configured strategy.

    :param locations: The original image location list.
    :param kwargs: Strategy-specific arguments for under layer strategy module.
    :returns: The best location from image location list.
    """
    locations = get_ordered_locations(locations, **kwargs)
    if locations:
        return locations[0]
    else:
        return None
