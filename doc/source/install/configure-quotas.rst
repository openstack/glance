* In the ``[oslo_limit]`` section, configure access to keystone:

  .. code-block:: ini

     [oslo_limit]
     auth_url = http://controller:5000
     auth_type = password
     user_domain_id = default
     username = glance
     system_scope = all
     password = GLANCE_PASS
     endpoint_id = 340be3625e9b4239a6415d034e98aace
     region_name = RegionOne

  .. end

  Replace ``GLANCE_PASS`` with the password you chose for the
  ``glance`` user in the Identity service.

  Make sure that the glance account has reader access to
  system-scope resources (like limits):

  .. code-block:: console

     $ openstack role add --user glance --user-domain Default --system all reader

  .. end

  See `the oslo_limit docs
  <https://docs.openstack.org/oslo.limit/latest/user/usage.html#configuration>`_
  for more information about configuring the unified limits client.

* In the ``[DEFAULT]`` section, optionally enable per-tenant quotas:

  .. path /etc/glance/glance.conf
  .. code-block:: ini

     [DEFAULT]
     use_keystone_limits = True

  .. end

  Note that you must have created the registered limits as
  described above if this is enabled.
