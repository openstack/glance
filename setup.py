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

from glance import version


if os.path.isdir('.bzr'):
    with open("glance/vcsversion.py", 'w') as version_file:
        vcs_cmd = subprocess.Popen(["bzr", "version-info", "--python"],
                                   stdout=subprocess.PIPE)
        vcsversion = vcs_cmd.communicate()[0]
        version_file.write(vcsversion)


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

cmdclass = {'sdist': local_sdist}

# If Sphinx is installed on the box running setup.py,
# enable setup.py to build the documentation, otherwise,
# just ignore it
try:
    from sphinx.setup_command import BuildDoc

    class local_BuildDoc(BuildDoc):
        def run(self):
            for builder in ['html', 'man']:
                self.builder = builder
                self.finalize_options()
                BuildDoc.run(self)
    cmdclass['build_sphinx'] = local_BuildDoc

except:
    pass


setup(
    name='glance',
    version=version.canonical_version_string(),
    description='The Glance project provides services for discovering, '
                'registering, and retrieving virtual machine images',
    license='Apache License (2.0)',
    author='OpenStack',
    author_email='openstack@lists.launchpad.net',
    url='http://glance.openstack.org/',
    packages=find_packages(exclude=['tests', 'bin']),
    test_suite='nose.collector',
    cmdclass=cmdclass,
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)',
    ],
    scripts=['bin/glance',
             'bin/glance-api',
             'bin/glance-cache-prefetcher',
             'bin/glance-cache-pruner',
             'bin/glance-cache-reaper',
             'bin/glance-control',
             'bin/glance-manage',
             'bin/glance-registry',
             'bin/glance-scrubber',
             'bin/glance-upload'])
