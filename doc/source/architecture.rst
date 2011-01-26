..
      Copyright 2010 OpenStack, LLC
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

Glance Architecture
===================

Glance is designed to be as adaptable as possible for various back-end storage
and registry database solutions. There is a main Glance API server
(the ``glance-api`` program) that serves as the communications hub between
various client programs, the registry of image metadata, and the storage
systems that actually contain the virtual machine image data.

From a birdseye perspective, one can visualize the Glance architectural model
like so:

.. graphviz::

  digraph birdseye {
    node [fontsize=10 fontname="Monospace"]
    a [label="Client A"]
    b [label="Client B"]
    c [label="Client C"]
    d [label="Glance API Server"]
    e [label="Registry Server"]
    f [label="Store Adapter"]
    g [label="S3 Store"]
    h [label="Swift Store"]
    i [label="Filesystem Store"]
    j [label="HTTP Store"]
    a -> d [dir=both]
    b -> d [dir=both]
    c -> d [dir=both]
    d -> e [dir=both]
    d -> f [dir=both]
    f -> g [dir=both]
    f -> h [dir=both]
    f -> i [dir=both]
    f -> j [dir=both]

  }

What is a Registry Server?
==========================

A registry server is any service that publishes image metadata that conforms
to the Glance Registry REST-ful API. Glance comes with a reference
implementation of a registry server called ``glance-registry``, but this is
only a reference implementation that uses a SQL database for its metdata
storage.

What is a Store?
================

A store is a Python class that inherits from ``glance.store.Backend`` and
conforms to that class' API for reading, writing, and deleting virtual
machine image data.

Glance currently ships with stores for S3, Swift, a simple filesystem store,
and a read-only HTTP(S) store.

Implementors are encouraged to create stores for other backends, including
other distributed storage systems like Sheepdog or Ceph.
