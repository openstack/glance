# Copyright 2015 OpenStack Foundation.
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
A mixin that validates the given body for jsonpatch-compatibility.
The methods supported are limited to listed in METHODS_ALLOWED
"""

import re

import jsonschema

import glance.common.exception as exc
from glance import i18n

_ = i18n._


class JsonPatchValidatorMixin(object):
    # a list of allowed methods allowed according to RFC 6902
    ALLOWED = ["replace", "test", "remove", "add", "copy"]
    PATH_REGEX_COMPILED = re.compile("^/[^/]+(/[^/]+)*$")

    def __init__(self, methods_allowed=["replace", "remove"]):
        self.schema = self._gen_schema(methods_allowed)
        self.methods_allowed = [m for m in methods_allowed
                                if m in self.ALLOWED]

    @staticmethod
    def _gen_schema(methods_allowed):
        """
        Generates a jsonschema for jsonpatch request based on methods_allowed
        """
        # op replace needs no 'value' param, so needs a special schema if
        # present in methods_allowed
        basic_schema = {
            "type": "array",
            "items": {"properties": {"op": {"type": "string",
                                            "enum": methods_allowed},
                                     "path": {"type": "string"},
                                     "value": {"type": ["string",
                                                        "object",
                                                        "integer",
                                                        "array",
                                                        "boolean"]}
                                     },
                      "required": ["op", "path", "value"],
                      "type": "object"},
            "$schema": "http://json-schema.org/draft-04/schema#"
        }
        if "remove" in methods_allowed:
            methods_allowed.remove("remove")
            no_remove_op_schema = {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": methods_allowed},
                    "path": {"type": "string"},
                    "value": {"type": ["string", "object",
                                       "integer", "array", "boolean"]}
                },
                "required": ["op", "path", "value"]}
            op_remove_only_schema = {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["remove"]},
                    "path": {"type": "string"}
                },
                "required": ["op", "path"]}

            basic_schema = {
                "type": "array",
                "items": {
                    "oneOf": [no_remove_op_schema, op_remove_only_schema]},
                "$schema": "http://json-schema.org/draft-04/schema#"
            }
        return basic_schema

    def validate_body(self, body):
        try:
            jsonschema.validate(body, self.schema)
            # now make sure everything is ok with path
            return [{"path": self._decode_json_pointer(e["path"]),
                     "value": e.get("value", None),
                     "op": e["op"]} for e in body]
        except jsonschema.ValidationError:
            raise exc.InvalidJsonPatchBody(body=body, schema=self.schema)

    def _check_for_path_errors(self, pointer):
        if not re.match(self.PATH_REGEX_COMPILED, pointer):
            msg = _("Json path should start with a '/', "
                    "end with no '/', no 2 subsequent '/' are allowed.")
            raise exc.InvalidJsonPatchPath(path=pointer, explanation=msg)
        if re.search('~[^01]', pointer) or pointer.endswith('~'):
            msg = _("Pointer contains '~' which is not part of"
                    " a recognized escape sequence [~0, ~1].")
            raise exc.InvalidJsonPatchPath(path=pointer, explanation=msg)

    def _decode_json_pointer(self, pointer):
        """Parses a json pointer. Returns a pointer as a string.

        Json Pointers are defined in
        http://tools.ietf.org/html/draft-pbryan-zyp-json-pointer .
        The pointers use '/' for separation between object attributes.
        A '/' character in an attribute name is encoded as "~1" and
        a '~' character is encoded as "~0".
        """
        self._check_for_path_errors(pointer)
        ret = []
        for part in pointer.lstrip('/').split('/'):
            ret.append(part.replace('~1', '/').replace('~0', '~').strip())
        return '/'.join(ret)
