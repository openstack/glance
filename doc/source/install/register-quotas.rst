If you decide to use per-tenant quotas in Glance, you must register
the limits in Keystone first:

.. code-block:: console

   $ openstack --os-cloud devstack-system-admin registered limit create \
     --service glance --default-limit 1000 --region RegionOne image_size_total

   +---------------+----------------------------------+
   | Field         | Value                            |
   +---------------+----------------------------------+
   | default_limit | 1000                             |
   | description   | None                             |
   | id            | 9cedfc5de80345a9b13ed00c2b5460f2 |
   | region_id     | RegionOne                        |
   | resource_name | image_size_total                 |
   | service_id    | e38c84a2487f49fd9864193bdc8a3174 |
   +---------------+----------------------------------+

   $ openstack --os-cloud devstack-system-admin registered limit create \
     --service glance --default-limit 1000 --region RegionOne image_stage_total

   +---------------+----------------------------------+
   | Field         | Value                            |
   +---------------+----------------------------------+
   | default_limit | 1000                             |
   | description   | None                             |
   | id            | 5a68712b6ba6496d823d0c66e5e860b9 |
   | region_id     | RegionOne                        |
   | resource_name | image_stage_total                |
   | service_id    | e38c84a2487f49fd9864193bdc8a3174 |
   +---------------+----------------------------------+

   $ openstack --os-cloud devstack-system-admin registered limit create \
     --service glance --default-limit 100 --region RegionOne image_count_total

   +---------------+----------------------------------+
   | Field         | Value                            |
   +---------------+----------------------------------+
   | default_limit | 100                              |
   | description   | None                             |
   | id            | beb91b043296499f8e6268f29d8b2749 |
   | region_id     | RegionOne                        |
   | resource_name | image_count_total                |
   | service_id    | e38c84a2487f49fd9864193bdc8a3174 |
   +---------------+----------------------------------+

   $ openstack --os-cloud devstack-system-admin registered limit create \
     --service glance --default-limit 100 --region RegionOne \
     image_count_uploading

   +---------------+----------------------------------+
   | Field         | Value                            |
   +---------------+----------------------------------+
   | default_limit | 100                              |
   | description   | None                             |
   | id            | fc29649c047a45bf9bc03ec4a7bcb8af |
   | region_id     | RegionOne                        |
   | resource_name | image_count_uploading            |
   | service_id    | e38c84a2487f49fd9864193bdc8a3174 |
   +---------------+----------------------------------+

.. end

Be sure to also set ``use_keystone_limits=True`` in your ``glance-api.conf``
file.
