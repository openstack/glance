# Copyright (c) 2014 Mirantis, Inc.
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

from glance.contrib.plugins.image_artifact.v1 import image as v1
from glance.contrib.plugins.image_artifact.v1_1 import image as v1_1
from glance.contrib.plugins.image_artifact.v2 import image as v2

versions = [v1.ImageAsAnArtifact, v1_1.ImageAsAnArtifact, v2.ImageAsAnArtifact]
