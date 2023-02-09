..
 This work is licensed under a Creative Commons Attribution 3.0 Unported
 License.

 http://creativecommons.org/licenses/by/3.0/legalcode

=========================================
Secure Hash Algorithm Support (Multihash)
=========================================

The Secure Hash Algorithm feature supplements the current ‘checksum’
image property with a self-describing secure hash.

The self-description consists of two new image properties:

``os_hash_algo``
   Contains the name of the secure hash algorithm used to generate the value on
   the image

``os_hash_value``
   The hexdigest computed by applying the secure hash algorithm named in the
   ``os_hash_algo`` property to the image data

Hash Algorithm Configuration
============================

``os_hash_algo`` will be populated by the value of the configuration option
``hashing_algorithm`` in the ``glance.conf`` file. The ``os_hash_value`` value
will be populated by the hexdigest computed when the algorithm is applied to
the uploaded or imported image data.

These are read-only image properties and are not user-modifiable.

The default secure hash algorithm is SHA-512. It should be suitable for most
applications.

The multihash is computed only for new images. There is no provision for
computing the multihash for existing images.
