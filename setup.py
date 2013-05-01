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

import setuptools

from glance.openstack.common import setup

requires = setup.parse_requirements()
depend_links = setup.parse_dependency_links()
project = 'glance'

setuptools.setup(
    name=project,
    version=setup.get_version(project, '2013.2'),
    description='The Glance project provides services for discovering, '
                'registering, and retrieving virtual machine images',
    license='Apache License (2.0)',
    author='OpenStack',
    author_email='openstack@lists.launchpad.net',
    url='http://glance.openstack.org/',
    packages=setuptools.find_packages(exclude=['bin']),
    test_suite='nose.collector',
    cmdclass=setup.get_cmdclass(),
    include_package_data=True,
    install_requires=requires,
    dependency_links=depend_links,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)',
        'Environment :: OpenStack',
    ],
    entry_points={'console_scripts':
                  ['glance-api=glance.cmd.api:main',
                   'glance-cache-prefetcher=glance.cmd.cache_prefetcher:main',
                   'glance-cache-pruner = glance.cmd.cache_pruner:main',
                   'glance-cache-manage = glance.cmd.cache_manage:main',
                   'glance-cache-cleaner = glance.cmd.cache_cleaner:main',
                   'glance-control = glance.cmd.control:main',
                   'glance-manage = glance.cmd.manage:main',
                   'glance-registry = glance.cmd.registry:main',
                   'glance-replicator = glance.cmd.replicator:main',
                   'glance-scrubber = glance.cmd.scrubber:main']},
    py_modules=[])
