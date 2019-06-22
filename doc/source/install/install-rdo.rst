Install and configure (Red Hat)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section describes how to install and configure the Image service,
code-named glance, on the controller node. For simplicity, this
configuration stores images on the local file system.

Prerequisites
-------------

Before you install and configure the Image service, you must
create a database, service credentials, and API endpoints.

#. To create the database, complete these steps:

   * Use the database access client to connect to the database
     server as the ``root`` user:

     .. code-block:: console

        $ mysql -u root -p

     .. end

   * Create the ``glance`` database:

     .. code-block:: console

        MariaDB [(none)]> CREATE DATABASE glance;

     .. end

   * Grant proper access to the ``glance`` database:

     .. code-block:: console

        MariaDB [(none)]> GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'localhost' \
          IDENTIFIED BY 'GLANCE_DBPASS';
        MariaDB [(none)]> GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' \
          IDENTIFIED BY 'GLANCE_DBPASS';

     .. end

     Replace ``GLANCE_DBPASS`` with a suitable password.

   * Exit the database access client.

#. Source the ``admin`` credentials to gain access to
   admin-only CLI commands:

   .. code-block:: console

      $ . admin-openrc

   .. end

#. To create the service credentials, complete these steps:

   * Create the ``glance`` user:

     .. code-block:: console

        $ openstack user create --domain default --password-prompt glance

        User Password:
        Repeat User Password:
        +---------------------+----------------------------------+
        | Field               | Value                            |
        +---------------------+----------------------------------+
        | domain_id           | default                          |
        | enabled             | True                             |
        | id                  | 3f4e777c4062483ab8d9edd7dff829df |
        | name                | glance                           |
        | options             | {}                               |
        | password_expires_at | None                             |
        +---------------------+----------------------------------+

     .. end

   * Add the ``admin`` role to the ``glance`` user and
     ``service`` project:

     .. code-block:: console

        $ openstack role add --project service --user glance admin

     .. end

     .. note::

        This command provides no output.

   * Create the ``glance`` service entity:

     .. code-block:: console

        $ openstack service create --name glance \
          --description "OpenStack Image" image

        +-------------+----------------------------------+
        | Field       | Value                            |
        +-------------+----------------------------------+
        | description | OpenStack Image                  |
        | enabled     | True                             |
        | id          | 8c2c7f1b9b5049ea9e63757b5533e6d2 |
        | name        | glance                           |
        | type        | image                            |
        +-------------+----------------------------------+

     .. end

#. Create the Image service API endpoints:

   .. code-block:: console

      $ openstack endpoint create --region RegionOne \
        image public http://controller:9292

      +--------------+----------------------------------+
      | Field        | Value                            |
      +--------------+----------------------------------+
      | enabled      | True                             |
      | id           | 340be3625e9b4239a6415d034e98aace |
      | interface    | public                           |
      | region       | RegionOne                        |
      | region_id    | RegionOne                        |
      | service_id   | 8c2c7f1b9b5049ea9e63757b5533e6d2 |
      | service_name | glance                           |
      | service_type | image                            |
      | url          | http://controller:9292           |
      +--------------+----------------------------------+

      $ openstack endpoint create --region RegionOne \
        image internal http://controller:9292

      +--------------+----------------------------------+
      | Field        | Value                            |
      +--------------+----------------------------------+
      | enabled      | True                             |
      | id           | a6e4b153c2ae4c919eccfdbb7dceb5d2 |
      | interface    | internal                         |
      | region       | RegionOne                        |
      | region_id    | RegionOne                        |
      | service_id   | 8c2c7f1b9b5049ea9e63757b5533e6d2 |
      | service_name | glance                           |
      | service_type | image                            |
      | url          | http://controller:9292           |
      +--------------+----------------------------------+

      $ openstack endpoint create --region RegionOne \
        image admin http://controller:9292

      +--------------+----------------------------------+
      | Field        | Value                            |
      +--------------+----------------------------------+
      | enabled      | True                             |
      | id           | 0c37ed58103f4300a84ff125a539032d |
      | interface    | admin                            |
      | region       | RegionOne                        |
      | region_id    | RegionOne                        |
      | service_id   | 8c2c7f1b9b5049ea9e63757b5533e6d2 |
      | service_name | glance                           |
      | service_type | image                            |
      | url          | http://controller:9292           |
      +--------------+----------------------------------+

   .. end

Install and configure components
--------------------------------

.. include:: note_configuration_vary_by_distribution.txt




#. Install the packages:

   .. code-block:: console

      # yum install openstack-glance

   .. end



2. Edit the ``/etc/glance/glance-api.conf`` file and complete the
   following actions:

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

        [glance_store]
        # ...
        stores = file,http
        default_store = file
        filesystem_store_datadir = /var/lib/glance/images/

     .. end


3. Populate the Image service database:

   .. code-block:: console

      # su -s /bin/sh -c "glance-manage db_sync" glance

   .. end

   .. note::

      Ignore any deprecation messages in this output.


Finalize installation
---------------------


* Start the Image services and configure them to start when
  the system boots:

  .. code-block:: console

     # systemctl enable openstack-glance-api.service
     # systemctl start openstack-glance-api.service

  .. end


