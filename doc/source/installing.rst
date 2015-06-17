..
      Copyright 2011 OpenStack Foundation
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

Installation
============

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

Only RHEL 6, Fedora 18, and newer releases have the necessary
components packaged.
On RHEL 6, enable the EPEL repository.

Install Glance::

   $ su -
   # yum install openstack-glance

openSUSE, SLE
#############

openSUSE 13.2, SLE 12, and the rolling release Factory needs an extra
repository enabled to install all the OpenStack packages.

Search the proper repository in the `Cloud:OpenStack:Master <https://build.opensuse.org/project/repositories/Cloud:OpenStack:Master>`_ project. For example, for openSUSE 13.2:

1. Add the OpenStack master repository::

   $ sudo zypper ar -f -g http://download.opensuse.org/repositories/Cloud:/OpenStack:/Master/openSUSE_13.2/ OpenStack
   $ sudo zypper ref

2. Install Glance::

   $ sudo zypper in openstack-glance

Installing from source tarballs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To install the latest version of Glance from the Launchpad Bazaar repositories,
follow the following instructions.

1. Grab the source tarball from `Launchpad <http://launchpad.net/glance/+download>`_

2. Untar the source tarball::

   $> tar -xzf <FILE>

3. Change into the package directory and build/install::

   $> cd glance-<RELEASE>
   $> sudo python setup.py install

Installing from Git
~~~~~~~~~~~~~~~~~~~

To install the latest version of Glance from the GitHub Git repositories,
follow the following instructions.

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
   # yum install python-webob python-eventlet
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

openSUSE, SLE
#############

On openSUSE and SLE (also this is valid for Factory), we can install
all the build dependencies using Zypper.

1. Install Git and build dependencies::

   $ sudo zypper install git
   $ sudo zypper source-install -d openstack-glance

.. note::

   If you want to build the Glance documentation locally, you will also want
   to install the packages python-sphinx and graphviz.

2. Clone Glance's trunk branch from GitHub::

   $ git clone git://github.com/openstack/glance
   $ cd glance

3. Install Glance::

   $ sudo python setup.py install
