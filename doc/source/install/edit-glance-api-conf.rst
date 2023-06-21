* In the ``[database]`` section, configure database access:

  .. path /etc/glance/glance.conf
  .. code-block:: ini

     [database]
     # ...
     connection = mysql+pymysql://glance:GLANCE_DBPASS@controller/glance

  .. end

  Replace ``GLANCE_DBPASS`` with the password you chose for the
  Image service database.

* In the ``[keystone_authtoken]`` and ``[paste_deploy]`` sections,
  configure Identity service access:

  .. path /etc/glance/glance.conf
  .. code-block:: ini

     [keystone_authtoken]
     # ...
     www_authenticate_uri  = http://controller:5000
     auth_url = http://controller:5000
     memcached_servers = controller:11211
     auth_type = password
     project_domain_name = Default
     user_domain_name = Default
     project_name = service
     username = glance
     password = GLANCE_PASS

     [paste_deploy]
     # ...
     flavor = keystone

  .. end

  Replace ``GLANCE_PASS`` with the password you chose for the
  ``glance`` user in the Identity service.

  .. note::

     Comment out or remove any other options in the
     ``[keystone_authtoken]`` section.

* In the ``[glance_store]`` section, configure the local file
  system store and location of image files:

  .. path /etc/glance/glance.conf
  .. code-block:: ini

     [DEFAULT]
     # ...
     enabled_backends=fs:file

     [glance_store]
     # ...
     default_backend = fs

     [fs]
     filesystem_store_datadir = /var/lib/glance/images/

  .. end

.. include:: configure-quotas.rst
