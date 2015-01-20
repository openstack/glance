# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import glance.common.exception as exc
import glance.common.jsonpatchvalidator as jpv
import glance.tests.utils as utils


class TestValidator(jpv.JsonPatchValidatorMixin):
    def __init__(self, methods_allowed=["replace", "add"]):
        super(TestValidator, self).__init__(methods_allowed)


class TestJsonPatchMixin(utils.BaseTestCase):
    def test_body_validation(self):
        validator = TestValidator()
        validator.validate_body(
            [{"op": "replace", "path": "/param", "value": "ok"}])
        # invalid if not a list of [{"op": "", "path": "", "value": ""}]
        # is passed
        self.assertRaises(exc.JsonPatchException, validator.validate_body,
                          {"op": "replace", "path": "/me",
                           "value": "should be a list"})

    def test_value_validation(self):
        # a string, a list and a dict are valid value types
        validator = TestValidator()
        validator.validate_body(
            [{"op": "replace", "path": "/param", "value": "ok string"}])
        validator.validate_body(
            [{"op": "replace", "path": "/param",
              "value": ["ok list", "really ok"]}])
        validator.validate_body(
            [{"op": "replace", "path": "/param", "value": {"ok": "dict"}}])

    def test_op_validation(self):
        validator = TestValidator(methods_allowed=["replace", "add", "copy"])
        validator.validate_body(
            [{"op": "copy", "path": "/param", "value": "ok"},
             {"op": "replace", "path": "/param/1", "value": "ok"}])
        self.assertRaises(
            exc.JsonPatchException, validator.validate_body,
            [{"op": "test", "path": "/param", "value": "not allowed"}])
        self.assertRaises(exc.JsonPatchException, validator.validate_body,
                          [{"op": "nosuchmethodatall", "path": "/param",
                           "value": "no way"}])

    def test_path_validation(self):
        validator = TestValidator()
        bad_body_part = {"op": "add", "value": "bad path"}
        for bad_path in ["/param/", "param", "//param", "/param~2", "/param~"]:
            bad_body_part["path"] = bad_path
            bad_body = [bad_body_part]
            self.assertRaises(exc.JsonPatchException,
                              validator.validate_body, bad_body)
        ok_body = [{"op": "add", "value": "some value",
                    "path": "/param~1/param~0"}]
        body = validator.validate_body(ok_body)[0]
        self.assertEqual("param//param~", body["path"])
