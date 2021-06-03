* In the ``[oslo_limit]`` section, configure access to keystone:

  .. code-block:: ini

     [oslo_limit]
     auth_url = http://controller:5000
     auth_type = password
     user_domain_id = default
     username = MY_SERVICE
     system_scope = all
     password = MY_PASSWORD
     endpoint_id = ENDPOINT_ID
     region_name = RegionOne

  .. end

  Make sure that the MY_SERVICE account has reader access to
  system-scope resources (like limits):

  .. code-block:: console

     $ openstack role add --user MY_SERVICE --user-domain Default --system all reader

  .. end

  See `the oslo_limit docs
  <https://docs.openstack.org/oslo.limit/latest/user/usage.html#configuration>`_
  for more information about configuring the unified limits client.

* In the ``[DEFAULT]`` section, optionally enable per-tenant quotas:

  .. path /etc/glance/glance.conf
  .. code-block:: ini

     [DEFAULT]
     use_keystone_quotas = True

  .. end

  Note that you must have created the registered limits as
  described above if this is enabled.
