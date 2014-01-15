# Copyright 2012, Piston Cloud Computing, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


def validate(filter, value):
    return FILTER_FUNCTIONS.get(filter, lambda v: True)(value)


def validate_int_in_range(min=0, max=None):
    def _validator(v):
        try:
            if max is None:
                return min <= int(v)
            return min <= int(v) <= max
        except ValueError:
            return False
    return _validator


def validate_boolean(v):
    return v.lower() in ('none', 'true', 'false', '1', '0')


FILTER_FUNCTIONS = {'size_max': validate_int_in_range(),  # build validator
                    'size_min': validate_int_in_range(),  # build validator
                    'min_ram': validate_int_in_range(),  # build validator
                    'protected': validate_boolean,
                    'is_public': validate_boolean, }
