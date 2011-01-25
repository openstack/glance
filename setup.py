#!/usr/bin/python
# Copyright (c) 2010 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess

from setuptools import setup, find_packages
from setuptools.command.sdist import sdist
from sphinx.setup_command import BuildDoc


class local_BuildDoc(BuildDoc):
    def run(self):
        for builder in ['html', 'man']:
            self.builder = builder
            self.finalize_options()
            BuildDoc.run(self)


class local_sdist(sdist):
    """Customized sdist hook - builds the ChangeLog file from VC first"""

    def run(self):
        if os.path.isdir('.bzr'):
            # We're in a bzr branch

            log_cmd = subprocess.Popen(["bzr", "log", "--gnu"],
                                       stdout=subprocess.PIPE)
            changelog = log_cmd.communicate()[0]
            with open("ChangeLog", "w") as changelog_file:
                changelog_file.write(changelog)
        sdist.run(self)


name = 'glance'
version = '0.1.5'

cmdclass = {'sdist': local_sdist,
            'build_sphinx': local_BuildDoc}

setup(
    name=name,
    version=version,
    description='Glance',
    license='Apache License (2.0)',
    author='OpenStack, LLC.',
    author_email='openstack-admins@lists.launchpad.net',
    url='https://launchpad.net/glance',
    packages=find_packages(exclude=['tests', 'bin']),
    test_suite='nose.collector',
    cmdclass=cmdclass,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)',
    ],
    install_requires=[],  # removed for better compat
    scripts=['bin/glance-api',
             'bin/glance-registry',
             'bin/glance-upload'])
