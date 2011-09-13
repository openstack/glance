# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Reference implementation registry server WSGI controller
"""

import json
import logging

import routes
from webob import exc

from glance.common import exception
from glance.common import utils
from glance.common import wsgi
from glance.registry.db import api as db_api


logger = logging.getLogger('glance.registry.server')

DISPLAY_FIELDS_IN_INDEX = ['id', 'name', 'size',
                           'disk_format', 'container_format',
                           'checksum']

SUPPORTED_FILTERS = ['name', 'status', 'container_format', 'disk_format',
                     'size_min', 'size_max']

SUPPORTED_SORT_KEYS = ('name', 'status', 'container_format', 'disk_format',
                       'size', 'id', 'created_at', 'updated_at')

SUPPORTED_SORT_DIRS = ('asc', 'desc')

SUPPORTED_PARAMS = ('limit', 'marker', 'sort_key', 'sort_dir')


class Controller(object):
    """Controller for the reference implementation registry server"""

    def __init__(self, options):
        self.options = options
        db_api.configure_db(options)

    def _get_images(self, context, **params):
        """
        Get images, wrapping in exception if necessary.
        """
        try:
            return db_api.image_get_all(context, **params)
        except exception.NotFound, e:
            msg = _("Invalid marker. Image could not be found.")
            raise exc.HTTPBadRequest(explanation=msg)

    def index(self, req):
        """
        Return a basic filtered list of public, non-deleted images

        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings::

            {
            'id': <ID>,
            'name': <NAME>,
            'size': <SIZE>,
            'disk_format': <DISK_FORMAT>,
            'container_format': <CONTAINER_FORMAT>,
            'checksum': <CHECKSUM>
            }
        """
        params = self._get_query_params(req)
        images = self._get_images(req.context, **params)

        results = []
        for image in images:
            result = {}
            for field in DISPLAY_FIELDS_IN_INDEX:
                result[field] = image[field]
            results.append(result)
        return dict(images=results)

    def detail(self, req):
        """
        Return a filtered list of public, non-deleted images in detail

        :param req: the Request object coming from the wsgi layer
        :retval a mapping of the following form::

            dict(images=[image_list])

        Where image_list is a sequence of mappings containing
        all image model fields.
        """
        params = self._get_query_params(req)

        images = self._get_images(req.context, **params)
        image_dicts = [make_image_dict(i) for i in images]
        return dict(images=image_dicts)

    def _get_query_params(self, req):
        """
        Extract necessary query parameters from http request.

        :param req: the Request object coming from the wsgi layer
        :retval dictionary of filters to apply to list of images
        """
        params = {
            'filters': self._get_filters(req),
            'limit': self._get_limit(req),
            'sort_key': self._get_sort_key(req),
            'sort_dir': self._get_sort_dir(req),
            'marker': self._get_marker(req),
        }

        for key, value in params.items():
            if value is None:
                del params[key]

        return params

    def _get_filters(self, req):
        """
        Return a dictionary of query param filters from the request

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        filters = {}
        properties = {}

        if req.context.is_admin:
            # Only admin gets to look for non-public images
            filters['is_public'] = self._get_is_public(req)
            # The same for deleted
            filters['deleted'] = self._parse_deleted_filter(req)
        else:
            filters['is_public'] = True
            # NOTE(jkoelker): This is technically unnecessary since the db
            #                 api will force deleted=False if its not an
            #                 admin context. But explicit > implicit.
            filters['deleted'] = False
        for param in req.str_params:
            if param in SUPPORTED_FILTERS:
                filters[param] = req.str_params.get(param)
            if param.startswith('property-'):
                _param = param[9:]
                properties[_param] = req.str_params.get(param)

        if len(properties) > 0:
            filters['properties'] = properties

        return filters

    def _get_limit(self, req):
        """Parse a limit query param into something usable."""
        try:
            default = self.options['limit_param_default']
        except KeyError:
            # if no value is configured, provide a sane default
            default = 25
            msg = _("Failed to read limit_param_default from config. "
                    "Defaulting to %s") % default
            logger.debug(msg)

        try:
            limit = int(req.str_params.get('limit', default))
        except ValueError:
            raise exc.HTTPBadRequest(_("limit param must be an integer"))

        if limit < 0:
            raise exc.HTTPBadRequest(_("limit param must be positive"))

        try:
            api_limit_max = int(self.options['api_limit_max'])
        except (KeyError, ValueError):
            api_limit_max = 1000
            msg = _("Failed to read api_limit_max from config. "
                    "Defaulting to %s") % api_limit_max
            logger.debug(msg)

        return min(api_limit_max, limit)

    def _get_marker(self, req):
        """Parse a marker query param into something usable."""
        marker = req.str_params.get('marker', None)

        if marker is None:
            return None

        try:
            marker = int(marker)
        except ValueError:
            raise exc.HTTPBadRequest(_("marker param must be an integer"))
        return marker

    def _get_sort_key(self, req):
        """Parse a sort key query param from the request object."""
        sort_key = req.str_params.get('sort_key', None)
        if sort_key is not None and sort_key not in SUPPORTED_SORT_KEYS:
            _keys = ', '.join(SUPPORTED_SORT_KEYS)
            msg = _("Unsupported sort_key. Acceptable values: %s") % (_keys,)
            raise exc.HTTPBadRequest(explanation=msg)
        return sort_key

    def _get_sort_dir(self, req):
        """Parse a sort direction query param from the request object."""
        sort_dir = req.str_params.get('sort_dir', None)
        if sort_dir is not None and sort_dir not in SUPPORTED_SORT_DIRS:
            _keys = ', '.join(SUPPORTED_SORT_DIRS)
            msg = _("Unsupported sort_dir. Acceptable values: %s") % (_keys,)
            raise exc.HTTPBadRequest(explanation=msg)
        return sort_dir

    def _get_is_public(self, req):
        """Parse is_public into something usable."""
        is_public = req.str_params.get('is_public', None)

        if is_public is None:
            # NOTE(vish): This preserves the default value of showing only
            #             public images.
            return True
        is_public = is_public.lower()
        if is_public == 'none':
            return None
        elif is_public == 'true' or is_public == '1':
            return True
        elif is_public == 'false' or is_public == '0':
            return False
        else:
            raise exc.HTTPBadRequest(_("is_public must be None, True, "
                                       "or False"))

    def _parse_deleted_filter(self, req):
        """Parse deleted into something usable."""
        deleted = req.str_params.get('deleted', False)
        if not deleted:
            return False
        return utils.bool_from_string(deleted)

    def show(self, req, id):
        """Return data about the given image id."""
        try:
            image = db_api.image_get(req.context, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': id})
            logger.info(msg)
            raise exc.HTTPNotFound()

        return dict(image=make_image_dict(image))

    def delete(self, req, id):
        """
        Deletes an existing image with the registry.

        :param req: wsgi Request object
        :param id:  The opaque internal identifier for the image

        :retval Returns 200 if delete was successful, a fault if not.
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()

        try:
            db_api.image_destroy(req.context, id)
        except exception.NotFound:
            return exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': id})
            logger.info(msg)
            raise exc.HTTPNotFound()

    def create(self, req, body):
        """
        Registers a new image with the registry.

        :param req: wsgi Request object
        :param body: Dictionary of information about the image

        :retval Returns the newly-created image information as a mapping,
                which will include the newly-created image's internal id
                in the 'id' field
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()

        image_data = body['image']

        # Ensure the image has a status set
        image_data.setdefault('status', 'active')

        # Set up the image owner
        if not req.context.is_admin or 'owner' not in image_data:
            image_data['owner'] = req.context.owner

        try:
            image_data = db_api.image_create(req.context, image_data)
            return dict(image=make_image_dict(image_data))
        except exception.Duplicate:
            msg = (_("Image with identifier %s already exists!") % id)
            logger.error(msg)
            return exc.HTTPConflict(msg)
        except exception.Invalid, e:
            msg = (_("Failed to add image metadata. "
                     "Got error: %(e)s") % locals())
            logger.error(msg)
            return exc.HTTPBadRequest(msg)

    def update(self, req, id, body):
        """
        Updates an existing image with the registry.

        :param req: wsgi Request object
        :param body: Dictionary of information about the image
        :param id:  The opaque internal identifier for the image

        :retval Returns the updated image information as a mapping,
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()

        image_data = body['image']

        # Prohibit modification of 'owner'
        if not req.context.is_admin and 'owner' in image_data:
            del image_data['owner']

        purge_props = req.headers.get("X-Glance-Registry-Purge-Props", "false")
        try:
            logger.debug(_("Updating image %(id)s with metadata: "
                           "%(image_data)r") % locals())
            if purge_props == "true":
                updated_image = db_api.image_update(req.context, id,
                                                    image_data, True)
            else:
                updated_image = db_api.image_update(req.context, id,
                                                    image_data)
            return dict(image=make_image_dict(updated_image))
        except exception.Invalid, e:
            msg = (_("Failed to update image metadata. "
                     "Got error: %(e)s") % locals())
            logger.error(msg)
            return exc.HTTPBadRequest(msg)
        except exception.NotFound:
            raise exc.HTTPNotFound(body='Image not found',
                               request=req,
                               content_type='text/plain')
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': id})
            logger.info(msg)
            raise exc.HTTPNotFound(body='Image not found',
                               request=req,
                               content_type='text/plain')

    def members(self, req, image_id):
        """
        Get the members of an image.
        """
        try:
            image = db_api.image_get(req.context, image_id)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise exc.HTTPNotFound()

        return dict(members=make_member_list(image['members'],
                                             member_id='member',
                                             can_share='can_share'))

    def shared_images(self, req, member):
        """
        Retrieves images shared with the given member.
        """
        params = {}
        try:
            memberships = db_api.image_member_get_memberships(req.context,
                                                              member,
                                                              **params)
        except exception.NotFound, e:
            msg = _("Invalid marker. Membership could not be found.")
            raise exc.HTTPBadRequest(explanation=msg)

        return dict(shared_images=make_member_list(memberships,
                                                   image_id='image_id',
                                                   can_share='can_share'))

    def replace_members(self, req, image_id, body):
        """
        Replaces the members of the image with those specified in the
        body.  The body is a dict with the following format::

            {"memberships": [
                {"member_id": <MEMBER_ID>,
                 ["can_share": [True|False]]}, ...
            ]}
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()
        elif req.context.owner is None:
            raise exc.HTTPUnauthorized(_("No authenticated user"))

        # Make sure the image exists
        session = db_api.get_session()
        try:
            image = db_api.image_get(req.context, image_id, session=session)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise exc.HTTPNotFound()

        # Can they manipulate the membership?
        if not req.context.is_image_sharable(image):
            raise exc.HTTPForbidden(_("No permission to share that image"))

        # Get the membership list
        try:
            memb_list = body['memberships']
        except Exception, e:
            # Malformed entity...
            msg = _("Invalid membership association: %s") % e
            raise exc.HTTPBadRequest(explanation=msg)

        add = []
        existing = {}
        # Walk through the incoming memberships
        for memb in memb_list:
            try:
                datum = dict(image_id=image['id'],
                             member=memb['member_id'],
                             can_share=None)
            except Exception, e:
                # Malformed entity...
                msg = _("Invalid membership association: %s") % e
                raise exc.HTTPBadRequest(explanation=msg)

            # Figure out what can_share should be
            if 'can_share' in memb:
                datum['can_share'] = bool(memb['can_share'])

            # Try to find the corresponding membership
            try:
                membership = db_api.image_member_find(req.context,
                                                      datum['image_id'],
                                                      datum['member'],
                                                      session=session)

                # Are we overriding can_share?
                if datum['can_share'] is None:
                    datum['can_share'] = membership['can_share']

                existing[membership['id']] = {
                    'values': datum,
                    'membership': membership,
                    }
            except exception.NotFound:
                # Default can_share
                datum['can_share'] = bool(datum['can_share'])
                add.append(datum)

        # We now have a filtered list of memberships to add and
        # memberships to modify.  Let's start by walking through all
        # the existing image memberships...
        for memb in image['members']:
            if memb['id'] in existing:
                # Just update the membership in place
                update = existing[memb['id']]['values']
                db_api.image_member_update(req.context, memb, update,
                                           session=session)
            else:
                # Outdated one; needs to be deleted
                db_api.image_member_delete(req.context, memb, session=session)

        # Now add the non-existant ones
        for memb in add:
            db_api.image_member_create(req.context, memb, session=session)

        # Make an appropriate result
        return exc.HTTPNoContent()

    def add_member(self, req, image_id, member, body=None):
        """
        Adds a membership to the image, or updates an existing one.
        If a body is present, it is a dict with the following format::

            {"member": {
                "can_share": [True|False]
            }}

        If "can_share" is provided, the member's ability to share is
        set accordingly.  If it is not provided, existing memberships
        remain unchanged and new memberships default to False.
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()
        elif req.context.owner is None:
            raise exc.HTTPUnauthorized(_("No authenticated user"))

        # Make sure the image exists
        try:
            image = db_api.image_get(req.context, image_id)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise exc.HTTPNotFound()

        # Can they manipulate the membership?
        if not req.context.is_image_sharable(image):
            raise exc.HTTPForbidden(_("No permission to share that image"))

        # Determine the applicable can_share value
        can_share = None
        if body:
            try:
                can_share = bool(body['member']['can_share'])
            except Exception, e:
                # Malformed entity...
                msg = _("Invalid membership association: %s") % e
                raise exc.HTTPBadRequest(explanation=msg)

        # Look up an existing membership...
        try:
            session = db_api.get_session()
            membership = db_api.image_member_find(req.context,
                                                  image_id, member,
                                                  session=session)
            if can_share is not None:
                values = dict(can_share=can_share)
                db_api.image_member_update(req.context, membership, values,
                                           session=session)
        except exception.NotFound:
            values = dict(image_id=image['id'], member=member,
                          can_share=bool(can_share))
            db_api.image_member_create(req.context, values, session=session)

        # Make an appropriate result
        return exc.HTTPNoContent()

    def delete_member(self, req, image_id, member):
        """
        Removes a membership from the image.
        """
        if req.context.read_only:
            raise exc.HTTPForbidden()
        elif req.context.owner is None:
            raise exc.HTTPUnauthorized(_("No authenticated user"))

        # Make sure the image exists
        try:
            image = db_api.image_get(req.context, image_id)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        except exception.NotAuthorized:
            # If it's private and doesn't belong to them, don't let on
            # that it exists
            msg = _("Access by %(user)s to image %(id)s "
                    "denied") % ({'user': req.context.user,
                    'id': image_id})
            logger.info(msg)
            raise exc.HTTPNotFound()

        # Can they manipulate the membership?
        if not req.context.is_image_sharable(image):
            raise exc.HTTPForbidden(_("No permission to share that image"))

        # Look up an existing membership
        try:
            session = db_api.get_session()
            member_ref = db_api.image_member_find(req.context,
                                                  image_id,
                                                  member,
                                                  session=session)
            db_api.image_member_delete(req.context,
                                       member_ref,
                                       session=session)
        except exception.NotFound:
            pass

        # Make an appropriate result
        return exc.HTTPNoContent()


def create_resource(controller):
    """Images resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = wsgi.JSONResponseSerializer()
    return wsgi.Resource(controller, deserializer, serializer)


class API(wsgi.Router):
    """WSGI entry point for all Registry requests."""

    def __init__(self, options):
        mapper = routes.Mapper()
        resource = create_resource(Controller(options))
        mapper.resource("image", "images", controller=resource,
                        collection={'detail': 'GET'})
        mapper.connect("/", controller=resource, action="index")
        mapper.connect("/shared-images/{member}",
                       controller=resource, action="shared_images")
        mapper.connect("/images/{image_id}/members",
                       controller=resource, action="members",
                       conditions=dict(method=["GET"]))
        mapper.connect("/images/{image_id}/members",
                       controller=resource, action="replace_members",
                       conditions=dict(method=["PUT"]))
        mapper.connect("/images/{image_id}/members/{member}",
                       controller=resource, action="add_member",
                       conditions=dict(method=["PUT"]))
        mapper.connect("/images/{image_id}/members/{member}",
                       controller=resource, action="delete_member",
                       conditions=dict(method=["DELETE"]))
        super(API, self).__init__(mapper)


def make_image_dict(image):
    """
    Create a dict representation of an image which we can use to
    serialize the image.
    """

    def _fetch_attrs(d, attrs):
        return dict([(a, d[a]) for a in attrs
                    if a in d.keys()])

    # TODO(sirp): should this be a dict, or a list of dicts?
    # A plain dict is more convenient, but list of dicts would provide
    # access to created_at, etc
    properties = dict((p['name'], p['value'])
                      for p in image['properties'] if not p['deleted'])

    image_dict = _fetch_attrs(image, db_api.IMAGE_ATTRS)

    image_dict['properties'] = properties
    return image_dict


def make_member_list(members, **attr_map):
    """
    Create a dict representation of a list of members which we can use
    to serialize the members list.  Keyword arguments map the names of
    optional attributes to include to the database attribute.
    """

    def _fetch_memb(memb, attr_map):
        return dict([(k, memb[v]) for k, v in attr_map.items()
                                  if v in memb.keys()])

    # Return the list of members with the given attribute mapping
    return [_fetch_memb(memb, attr_map) for memb in members
            if not memb.deleted]


def app_factory(global_conf, **local_conf):
    """
    paste.deploy app factory for creating Glance reference implementation
    registry server apps
    """
    conf = global_conf.copy()
    conf.update(local_conf)
    return API(conf)
