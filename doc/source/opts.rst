=============================
 Glance Configuration Options
=============================

Glance uses the following configuration files for its various services.

* :ref:`glance-api.conf`
* :ref:`glance-cache.conf`
* :ref:`glance-registry.conf`
* :ref:`glance-manage.conf`
* :ref:`glance-scrubber.conf`

This documentation page provides a list of all possible options for each
configuration file.  Refer to :doc:`Basic Configuration <configuring>`
for a detailed guide in getting started with various option settings.

.. _glance-api.conf:

---------------
glance-api.conf
---------------

.. show-options:: glance.api
.. show-options:: glance.store

Additional Common Configuration
+++++++++++++++++++++++++++++++

This configuration file also includes options from the following common
libraries.

* :ref:`keystonemiddleware.auth_token`
* :ref:`oslo.concurrency`
* :ref:`oslo.messaging`
* :ref:`oslo.db`
* :ref:`oslo.db.concurrency`
* :ref:`oslo.policy`

.. _glance-cache.conf:

-----------------
glance-cache.conf
-----------------

.. show-options:: glance.cache

Additional Common Configuration
+++++++++++++++++++++++++++++++

This configuration file also includes options from the following common
libraries.

* :ref:`oslo.policy`
* :ref:`oslo.log`

.. _glance-registry.conf:

--------------------
glance-registry.conf
--------------------

This configuration file controls how the register server operates. More
information can be found in :ref:`configuring-the-glance-registry`.

.. show-options:: glance.registry

Additional Common Configuration
+++++++++++++++++++++++++++++++

This configuration file also includes options from the following common
libraries.

* glance.store

* :ref:`keystonemiddleware.auth_token`
* :ref:`oslo.messaging`
* :ref:`oslo.db`
* :ref:`oslo.db.concurrency`
* :ref:`oslo.policy`
* :ref:`oslo.log`

.. _glance-manage.conf:

------------------
glance-manage.conf
------------------

.. show-options:: glance.manage

Additional Common Configuration
+++++++++++++++++++++++++++++++

This configuration file also includes options from the following common
libraries.

* :ref:`oslo.db`
* :ref:`oslo.db.concurrency`
* :ref:`oslo.log`

.. _glance-scrubber.conf:

--------------------
glance-scrubber.conf
--------------------

.. show-options:: glance.scrubber

Additional Common Configuration
+++++++++++++++++++++++++++++++

This configuration file also includes options from the following common
libraries.

* :ref:`oslo.concurrency`
* :ref:`oslo.db`
* :ref:`oslo.db.concurrency`
* :ref:`oslo.log`
* :ref:`oslo.policy`

=======================
 Common Library Options
=======================

.. _keystonemiddleware.auth_token:

-------------------
Keystone Middleware
-------------------

Options from the `Keystone Middleware`_ library.

.. show-options:: keystonemiddleware.auth_token

.. _oslo.concurrency:

----------------
Oslo Concurrency
----------------

Options from the `Oslo Concurrency`_ library.

.. show-options:: oslo.concurrency

.. _oslo.db:

-------
Oslo DB
-------

Options from the `Oslo DB`_ library.

.. show-options:: oslo.db

.. _oslo.db.concurrency:

-------------------
Oslo DB Concurrency
-------------------

Options from Oslo DB Concurrency.

.. show-options:: oslo.db.concurrency

.. _oslo.log:

--------
Oslo Log
--------

Options from the `Oslo Log`_ library.

.. show-options:: oslo.log

.. _oslo.messaging:

--------------
Oslo Messaging
--------------

Options from the `Oslo Messaging`_ library.

.. show-options:: oslo.messaging

.. _oslo.policy:

-----------
Oslo Policy
-----------

Options from the `Oslo Policy`_ library.

.. show-options:: oslo.policy

.. _Keystone Middleware: http://docs.openstack.org/developer/keystonemiddleware/middlewarearchitecture.html#configuration-options
.. _Oslo Concurrency: http://docs.openstack.org/developer/oslo.concurrency/opts.html
.. _Oslo DB: http://docs.openstack.org/developer/oslo.db/opts.html
.. _Oslo Log: http://docs.openstack.org/developer/oslo.log/opts.html
.. _Oslo Policy: http://docs.openstack.org/developer/oslo.policy/opts.html
.. _Oslo Messaging: http://docs.openstack.org/developer/oslo.messaging/opts.html
