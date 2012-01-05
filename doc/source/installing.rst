..
      Copyright 2011 OpenStack, LLC
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Installing Glance
=================

Installing from packages
~~~~~~~~~~~~~~~~~~~~~~~~

To install the latest released version of Glance,
follow the following instructions.

Debian, Ubuntu
##############

1. Add the Glance PPA to your sources.lst::

   $> sudo add-apt-repository ppa:glance-core/trunk
   $> sudo apt-get update

2. Install Glance::

   $> sudo apt-get install glance

Red Hat, Fedora
###############

Only RHEL 6, Fedora 15, and newer releases have the necessary
components packaged.
On RHEL 6, enable the EPEL repository.

Install Glance::

   $ su -
   # yum install openstack-glance

Mac OSX
#######

.. todo:: No idea how to do install on Mac OSX. Somebody with a Mac should complete this section

Installing from source tarballs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To install the latest version of Glance from the Launchpad Bazaar repositories,
following the following instructions.

1. Grab the source tarball from `Launchpad <http://launchpad.net/glance/+download>`_

2. Untar the source tarball::

   $> tar -xzf <FILE>

3. Change into the package directory and build/install::

   $> cd glance-<RELEASE>
   $> sudo python setup.py install

Installing from Git
~~~~~~~~~~~~~~~~~~~

To install the latest version of Glance from the GitHub Git repositories,
following the following instructions.

Debian, Ubuntu
##############

1. Install Git and build dependencies::

   $> sudo apt-get install git
   $> sudo apt-get build-dep glance

.. note::

   If you want to build the Glance documentation locally, you will also want
   to install the python-sphinx package

2. Clone Glance's trunk branch from GitHub::
   
   $> git clone git://github.com/openstack/glance
   $> cd glance

3. Install Glance::
   
   $> sudo python setup.py install

Red Hat, Fedora
###############

On Fedora, most developers and essentially all users install packages.
Instructions below are not commonly used, and even then typically in a
throw-away VM.

Since normal build dependencies are resolved by mechanisms of RPM,
there is no one-line command to install everything needed by
the source repository in git. One common way to discover the dependencies
is to search for *BuildRequires:* in the specfile of openstack-glance
for the appropriate distro.

In case of Fedora 16, for example, do this::

   $ su -
   # yum install git
   # yum install python2-devel python-setuptools python-distutils-extra
   # yum install python-webob python-eventlet python-boto
   # yum install python-virtualenv

Build Glance::

   $ python setup.py build

If any missing modules crop up, install them with yum, then retry the build.

.. note::

   If you want to build the Glance documentation, you will also want
   to install the packages python-sphinx and graphviz, then run
   "python setup.py build_sphinx". Due to required features of
   python-sphinx 1.0 or better, documentation can only be built
   on Fedora 15 or later.

Test the build::

   $ ./run_tests.sh -s

Once Glance is built and tested, install it::

   $ su -
   # python setup.py install

Mac OSX
#######

.. todo:: No idea how to do install on Mac OSX. Somebody with a Mac should complete this section
