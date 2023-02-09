..
 This work is licensed under a Creative Commons Attribution 3.0 Unported
 License.

 http://creativecommons.org/licenses/by/3.0/legalcode

=========================================
Secure Hash Algorithm Support (Multihash)
=========================================

The Secure Hash Algorithm feature adds image properties that may be used to
verify image integrity based on its hash.

The Secure Hash consists of two new image properties:

``os_hash_algo``
   Contains the name of the secure hash algorithm
   used to generate the value on the image

``os_hash_value``
   The hexdigest computed by applying the
   secure hash algorithm named in the ``os_hash_algo`` property to
   the image data

Image Verification
==================

When Secure Hash is used, the Glance image properties will include the two
fields ``os_hash_algo`` and ``os_hash_value``. These two fields provide the
hashing algorithm used to calculate the secure hash, along with the hash value
calculated for the image.

These values can be used to verify the image integrity when used. For example,
an image and its properties may be viewed with the following::

  $ glance image-show fa33e3cd-5fe4-46df-a604-1e9b9438b420
 +------------------+----------------------------------------------------------------------------------+
 | Property         | Value                                                                            |
 +------------------+----------------------------------------------------------------------------------+
 | checksum         | ffa3dd42fae539dcd8fe72d429bc677b                                                 |
 | container_format | bare                                                                             |
 | created_at       | 2019-06-05T13:39:46Z                                                             |
 | disk_format      | qcow2                                                                            |
 | id               | fa33e3cd-5fe4-46df-a604-1e9b9438b420                                             |
 | min_disk         | 10                                                                               |
 | min_ram          | 1024                                                                             |
 | name             | fedora-30                                                                        |
 | os_hash_algo     | sha512                                                                           |
 | os_hash_value    | d9f99d22a6b6ea1e8b93379dd2080f51a7ed6885aa7d4c2f2262ea1054935e02c47b45f9b56aa7f5 |
 |                  | 5e61d149d06f4ff6de03efde24f9d6774baf35f08c5e9d92                                 |
 | os_hidden        | False                                                                            |
 | owner            | 0e82e8f863a4485fabfbed1b5b856cd7                                                 |
 | protected        | False                                                                            |
 | size             | 332267520                                                                        |
 | status           | active                                                                           |
 | tags             | []                                                                               |
 | updated_at       | 2019-06-07T11:41:12Z                                                             |
 | virtual_size     | Not available                                                                    |
 | visibility       | public                                                                           |
 +------------------+----------------------------------------------------------------------------------+

From that output, we can see the ``os_hash_algo`` property shows that
**sha512** was used to generate the multihash. The ``os_hash_value`` then shows
the generated hash value is::

 d9f99d22a6b6ea1e8b93379dd2080f51a7ed6885aa7d4c2f2262ea1054935e02c47b45f9b56aa7f55e61d149d06f4ff6de03efde24f9d6774baf35f08c5e9d92

When downloading the image, you may now use these values to be able to verify
the integrity of the image. For example::

  $ glance image-download fa33e3cd-5fe4-46df-a604-1e9b9438b420 --file fedora-30
  $ sha512sum fedora-30
  d9f99d22a6b6ea1e8b93379dd2080f51a7ed6885aa7d4c2f2262ea1054935e02c47b45f9b56aa7f55e61d149d06f4ff6de03efde24f9d6774baf35f08c5e9d92

Using the ``sha512sum`` command, we are able to calculate the hash locally on
the image and verify it matches what was expected. If the output were not to
match, that would indicate the image has somehow been modified or corrupted
since being uploaded to Glance, and should likely not be used.
