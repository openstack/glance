.. -*- rst -*-

Metadata definition tags
************************

Creates, lists, shows details for, updates, and deletes metadata
definition tags.

*Since API v2.2*


Create tag definition
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   POST /v2/metadefs/namespaces/{namespace_name}/tags/{tag_name}

Adds a tag to the list of namespace tag definitions.

Normal response codes: 201

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - tag_name: tag_name

There is no request body.


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - name: name-tag
   - updated_at: updated_at


Response Example
----------------

.. literalinclude:: samples/metadef-tag-create-response.json
   :language: json


Get tag definition
~~~~~~~~~~~~~~~~~~

.. rest_method::
   GET /v2/metadefs/namespaces/{namespace_name}/tags/{tag_name}

Gets a definition for a tag.

The response body shows a single tag entity.

Normal response codes: 200

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - tag_name: tag_name
   - namespace_name: namespace_name

There is no request body.

Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - name: name-tag
   - updated_at: updated_at


Response Example
----------------

.. literalinclude:: samples/metadef-tag-details-response.json
   :language: json


Update tag definition
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   PUT /v2/metadefs/namespaces/{namespace_name}/tags/{tag_name}

Renames a tag definition.

Normal response codes: 200

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - tag_name: tag_name
   - namespace_name: namespace_name
   - name: name-tag

Request Example
---------------

.. literalinclude:: samples/metadef-tag-update-request.json
   :language: json


Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - created_at: created_at
   - name: name-tag
   - updated_at: updated_at


Response Example
----------------

.. literalinclude:: samples/metadef-tag-update-response.json
   :language: json


Delete tag definition
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   DELETE /v2/metadefs/namespaces/{namespace_name}/tags/{tag_name}

Deletes a tag definition within a namespace.

.. note::
    If the namespace containing the tag is protected, that is, if the
    ``protected`` attribute of the namespace is ``true``, then you must first
    set the ``protected`` attribute to ``false`` on the namespace before you
    will be permitted to delete the tag.

    * If you try to delete a tag from a protected namespace, the call returns
      the ``403`` response code.
    * To change the ``protected`` attribute of a namespace, use the
      :ref:`Update namespace <v2-update-namespace>` call.

When you successfully delete a tag from a namespace, the response is empty and
the response code is ``204``.

Normal response codes: 204

Error response codes: 400, 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - tag_name: tag_name


Create tags
~~~~~~~~~~~

.. rest_method::  POST /v2/metadefs/namespaces/{namespace_name}/tags

Creates one or more tag definitions in a namespace.

Normal response codes: 201

Error response codes: 400, 401, 403, 404, 409


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - X-Openstack-Append: append
   - namespace_name: namespace_name
   - tags: tags

Request Example
---------------

.. literalinclude:: samples/metadef-tags-create-request.json
   :language: json

Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - name: name
   - tags: tags

Response Example
----------------

.. literalinclude:: samples/metadef-tags-create-response.json
   :language: json



List tags
~~~~~~~~~

.. rest_method::
   GET /v2/metadefs/namespaces/{namespace_name}/tags

Lists the tag definitions within a namespace.

To manually paginate through the list of tags, use the ``limit``
and ``marker`` parameters.

To sort the results of this operation use the ``sort_key`` and
``sort_dir`` parameters. The API uses the natural sort order of the
tag attribute of the ``sort_key`` parameter.


Normal response codes: 200

Error response codes: 401, 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name
   - limit: limit-tags
   - marker: marker-tags
   - sort_key: sort_key-tags
   - sort_dir: sort_dir

There is no request body.

Response Parameters
-------------------

.. rest_parameters:: metadefs-parameters.yaml

   - tags: tags


Response Example
----------------

.. literalinclude:: samples/metadef-tags-list-response.json
   :language: json


Delete all tag definitions
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::
   DELETE /v2/metadefs/namespaces/{namespace_name}/tags

Deletes all tag definitions within a namespace.

.. note::
    If the namespace containing the tags is protected, that is, if the
    ``protected`` attribute of the namespace is ``true``, then you must first
    set the ``protected`` attribute to ``false`` on the namespace before you
    will be permitted to delete the tags.  If you try to delete the tags
    from a protected namespace, the call returns the ``403`` response code.

When you successfully delete the tags from a namespace, the
response is empty and the response code is ``204``.

Normal response codes: 204

Error response codes: 403, 404


Request
-------

.. rest_parameters:: metadefs-parameters.yaml

   - namespace_name: namespace_name

There is no request body.

There is no response body.
