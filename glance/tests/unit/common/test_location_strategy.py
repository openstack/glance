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

import stevedore

from glance.common import location_strategy
from glance.common.location_strategy import location_order
from glance.common.location_strategy import store_type
from glance.tests.unit import base


class TestLocationStrategy(base.IsolatedUnitTest):
    """Test routines in glance.common.location_strategy"""

    def _set_original_strategies(self, original_strategies):
        for name in location_strategy._available_strategies.keys():
            if name not in original_strategies:
                del location_strategy._available_strategies[name]

    def setUp(self):
        super(TestLocationStrategy, self).setUp()
        original_strategies = ['location_order', 'store_type']
        self.addCleanup(self._set_original_strategies, original_strategies)

    def test_load_strategy_modules(self):
        modules = location_strategy._load_strategies()
        # By default we have two built-in strategy modules.
        self.assertEqual(2, len(modules))
        self.assertEqual(set(['location_order', 'store_type']),
                         set(modules.keys()))
        self.assertEqual(location_strategy._available_strategies, modules)

    def test_load_strategy_module_with_deduplicating(self):
        modules = ['module1', 'module2']

        def _fake_stevedore_extension_manager(*args, **kwargs):
            ret = lambda: None
            ret.names = lambda: modules
            return ret

        def _fake_stevedore_driver_manager(*args, **kwargs):
            ret = lambda: None
            ret.driver = lambda: None
            ret.driver.__name__ = kwargs['name']
            # Module 1 and 2 has a same strategy name
            ret.driver.get_strategy_name = lambda: 'module_name'
            ret.driver.init = lambda: None
            return ret

        self.stub = self.stubs.Set(stevedore.extension, "ExtensionManager",
                                   _fake_stevedore_extension_manager)
        self.stub = self.stubs.Set(stevedore.driver, "DriverManager",
                                   _fake_stevedore_driver_manager)

        loaded_modules = location_strategy._load_strategies()
        self.assertEqual(1, len(loaded_modules))
        self.assertEqual('module_name', loaded_modules.keys()[0])
        # Skipped module #2, duplicated one.
        self.assertEqual('module1', loaded_modules['module_name'].__name__)

    def test_load_strategy_module_with_init_exception(self):
        modules = ['module_init_exception', 'module_good']

        def _fake_stevedore_extension_manager(*args, **kwargs):
            ret = lambda: None
            ret.names = lambda: modules
            return ret

        def _fake_stevedore_driver_manager(*args, **kwargs):
            if kwargs['name'] == 'module_init_exception':
                raise Exception('strategy module failed to initialize.')
            else:
                ret = lambda: None
                ret.driver = lambda: None
                ret.driver.__name__ = kwargs['name']
                ret.driver.get_strategy_name = lambda: kwargs['name']
                ret.driver.init = lambda: None
            return ret

        self.stub = self.stubs.Set(stevedore.extension, "ExtensionManager",
                                   _fake_stevedore_extension_manager)
        self.stub = self.stubs.Set(stevedore.driver, "DriverManager",
                                   _fake_stevedore_driver_manager)

        loaded_modules = location_strategy._load_strategies()
        self.assertEqual(1, len(loaded_modules))
        self.assertEqual('module_good', loaded_modules.keys()[0])
        # Skipped module #1, initialize failed one.
        self.assertEqual('module_good', loaded_modules['module_good'].__name__)

    def test_verify_valid_location_strategy(self):
        for strategy_name in ['location_order', 'store_type']:
            self.config(location_strategy=strategy_name)
            location_strategy.verify_location_strategy()

    def test_verify_invalid_location_strategy(self):
        strategy = 'invalid_strategy'
        self.config(location_strategy=strategy)
        self.assertRaises(RuntimeError,
                          location_strategy.verify_location_strategy,
                          strategy)

    def test_get_ordered_locations_with_none_or_empty_locations(self):
        self.assertEqual([], location_strategy.get_ordered_locations(None))
        self.assertEqual([], location_strategy.get_ordered_locations([]))

    def test_get_ordered_locations(self):
        self.config(location_strategy='location_order')

        original_locs = [{'url': 'loc1'}, {'url': 'loc2'}]
        ordered_locs = location_strategy.get_ordered_locations(original_locs)

        # Original location list should remain unchanged
        self.assertNotEqual(id(original_locs), id(ordered_locs))
        self.assertEqual(original_locs, ordered_locs)

    def test_choose_best_location_with_none_or_empty_locations(self):
        self.assertIsNone(location_strategy.choose_best_location(None))
        self.assertIsNone(location_strategy.choose_best_location([]))

    def test_choose_best_location(self):
        self.config(location_strategy='location_order')

        original_locs = [{'url': 'loc1'}, {'url': 'loc2'}]
        best_loc = location_strategy.choose_best_location(original_locs)

        # Deep copy protect original location.
        self.assertNotEqual(id(original_locs), id(best_loc))
        self.assertEqual(original_locs[0], best_loc)


class TestLocationOrderStrategyModule(base.IsolatedUnitTest):
    """Test routines in glance.common.location_strategy.location_order"""

    def test_get_ordered_locations(self):
        original_locs = [{'url': 'loc1'}, {'url': 'loc2'}]
        ordered_locs = location_order.get_ordered_locations(original_locs)
        # The result will ordered by original natural order.
        self.assertEqual(original_locs, ordered_locs)


class TestStoreTypeStrategyModule(base.IsolatedUnitTest):
    """Test routines in glance.common.location_strategy.store_type"""

    def test_get_ordered_locations(self):
        self.config(store_type_preference=['  rbd', 'sheepdog ', ' filesystem',
                                           'swift  ', '  http  ', 's3'],
                    group='store_type_location_strategy')
        locs = [{'url': 'file://image0', 'metadata': {'idx': 3}},
                {'url': 'rbd://image1', 'metadata': {'idx': 0}},
                {'url': 's3://image2', 'metadata': {'idx': 7}},
                {'url': 'file://image3', 'metadata': {'idx': 4}},
                {'url': 'swift://image4', 'metadata': {'idx': 6}},
                {'url': 'cinder://image5', 'metadata': {'idx': 8}},
                {'url': 'file://image6', 'metadata': {'idx': 5}},
                {'url': 'rbd://image7', 'metadata': {'idx': 1}},
                {'url': 'sheepdog://image8', 'metadata': {'idx': 2}}]
        ordered_locs = store_type.get_ordered_locations(copy.deepcopy(locs))
        locs.sort(key=lambda loc: loc['metadata']['idx'])
        # The result will ordered by preferred store type order.
        self.assertEqual(ordered_locs, locs)

    def test_get_ordered_locations_with_invalid_store_name(self):
        self.config(store_type_preference=['  rbd', 'sheepdog ', 'invalid',
                                           'swift  ', '  http  ', 's3'],
                    group='store_type_location_strategy')
        locs = [{'url': 'file://image0', 'metadata': {'idx': 5}},
                {'url': 'rbd://image1', 'metadata': {'idx': 0}},
                {'url': 's3://image2', 'metadata': {'idx': 4}},
                {'url': 'file://image3', 'metadata': {'idx': 6}},
                {'url': 'swift://image4', 'metadata': {'idx': 3}},
                {'url': 'cinder://image5', 'metadata': {'idx': 7}},
                {'url': 'file://image6', 'metadata': {'idx': 8}},
                {'url': 'rbd://image7', 'metadata': {'idx': 1}},
                {'url': 'sheepdog://image8', 'metadata': {'idx': 2}}]
        ordered_locs = store_type.get_ordered_locations(copy.deepcopy(locs))
        locs.sort(key=lambda loc: loc['metadata']['idx'])
        # The result will ordered by preferred store type order.
        self.assertEqual(ordered_locs, locs)
