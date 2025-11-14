#    Copyright 2014 IBM Corp.
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

import sys
import urllib.parse as urlparse

import glance_store as store_api
from oslo_config import cfg
from oslo_log import log as logging

import glance.db as db_api
from glance.i18n import _LE, _LW
from glance import scrubber

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

RESTRICTED_URI_SCHEMAS = frozenset(['file', 'filesystem', 'swift+config'])


def check_reserved_stores(enabled_stores):
    for store in enabled_stores:
        if store.startswith("os_glance_"):
            return True
    return False


def safe_delete_from_backend(context, image_id, location):
    """
    Given a location, delete an image from the store and
    update location status to db.

    This function try to handle all known exceptions which might be raised
    by those calls on store and DB modules in its implementation.

    :param context: The request context
    :param image_id: The image identifier
    :param location: The image location entry
    """

    try:
        if CONF.enabled_backends:
            backend = location['metadata'].get('store')
            ret = store_api.delete(location['url'],
                                   backend,
                                   context=context)
        else:
            ret = store_api.delete_from_backend(location['url'],
                                                context=context)

        location['status'] = 'deleted'
        if 'id' in location:
            db_api.get_api().image_location_delete(context, image_id,
                                                   location['id'], 'deleted')
        return ret
    except store_api.NotFound:
        msg = ("The image data for %(iid)s was not found in the store. "
               "The image record has been updated to reflect "
               "this." % {'iid': image_id})
        LOG.warning(msg)
    except store_api.StoreDeleteNotSupported as e:
        LOG.warning(str(e))
    except store_api.UnsupportedBackend:
        exc_type = sys.exc_info()[0].__name__
        msg = (_LE('Failed to delete image %(image_id)s from store: %(exc)s') %
               dict(image_id=image_id, exc=exc_type))
        LOG.error(msg)


def schedule_delayed_delete_from_backend(context, image_id, location):
    """
    Given a location, schedule the deletion of an image location and
    update location status to db.

    :param context: The request context
    :param image_id: The image identifier
    :param location: The image location entry
    """

    db_queue = scrubber.get_scrub_queue()

    context = None

    ret = db_queue.add_location(image_id, location)
    if ret:
        location['status'] = 'pending_delete'
        if 'id' in location:
            # NOTE(zhiyan): New added image location entry will has no 'id'
            # field since it has not been saved to DB.
            db_api.get_api().image_location_delete(context, image_id,
                                                   location['id'],
                                                   'pending_delete')
        else:
            db_api.get_api().image_location_add(context, image_id, location)

    return ret


def delete_image_location_from_backend(context, image_id, location):
    """
    Given a location, immediately or schedule the deletion of an image
    location and update location status to db.

    :param context: The request context
    :param image_id: The image identifier
    :param location: The image location entry
    """

    deleted = False
    if CONF.delayed_delete:
        deleted = schedule_delayed_delete_from_backend(context,
                                                       image_id, location)
    if not deleted:
        # NOTE(zhiyan) If image metadata has not been saved to DB
        # such as uploading process failure then we can't use
        # location status mechanism to support image pending delete.
        safe_delete_from_backend(context, image_id, location)


def validate_external_location(uri):
    """
    Validate if URI of external location are supported.

    Only over non-local store types are OK, i.e. Swift,
    HTTP. Note the absence of 'file://' for security reasons,
    see LP bug #942118, 1400966, 'swift+config://' is also
    absent for security reasons, see LP bug #1334196.

    :param uri: The URI of external image location.
    :returns: Whether given URI of external image location are OK.
    """
    if not uri:
        return False

    # TODO(zhiyan): This function could be moved to glance_store.
    # TODO(gm): Use a whitelist of allowed schemes
    scheme = urlparse.urlparse(uri).scheme
    known_schemes = store_api.get_known_schemes()
    if CONF.enabled_backends:
        known_schemes = store_api.get_known_schemes_for_multi_store()

    return (scheme in known_schemes and
            scheme not in RESTRICTED_URI_SCHEMAS)


def _get_store_id_from_uri(uri):
    scheme = urlparse.urlparse(uri).scheme
    location_map = store_api.location.SCHEME_TO_CLS_BACKEND_MAP
    url_matched = False
    if scheme not in location_map:
        LOG.warning("Unknown scheme '%(scheme)s' found in uri '%(uri)s'", {
            'scheme': scheme, 'uri': uri})
        return
    for store in location_map[scheme]:
        store_instance = location_map[scheme][store]['store']
        url_prefix = store_instance.url_prefix
        if url_prefix and uri.startswith(url_prefix):
            url_matched = True
            break

    if url_matched:
        return u"%s" % store
    else:
        LOG.warning("Invalid location uri %s", uri)
        return


def update_store_in_locations(context, image, image_repo):
    store_updated = False
    for loc in image.locations:
        if (not loc['metadata'].get(
                'store') or loc['metadata'].get(
                'store') not in CONF.enabled_backends):
            if loc['url'].startswith("cinder://"):
                _update_cinder_location_and_store_id(context, loc)

            store_id = _get_store_id_from_uri(loc['url'])
            if store_id:
                if 'store' in loc['metadata']:
                    old_store = loc['metadata']['store']
                    if old_store != store_id:
                        LOG.debug("Store '%(old)s' has changed to "
                                  "'%(new)s' by operator, updating "
                                  "the same in the location of image "
                                  "'%(id)s'", {'old': old_store,
                                               'new': store_id,
                                               'id': image.image_id})

                store_updated = True
                loc['metadata']['store'] = store_id

        # Always check S3 credentials for credential rotation scenarios
        if loc['url'].startswith(('s3://', 's3+http://', 's3+https://')):
            if _update_s3_location_and_store_id(context, loc):
                store_updated = True

    if store_updated:
        image_repo.save(image)


def _update_cinder_location_and_store_id(context, loc):
    """Update store location of legacy images

    While upgrading from single cinder store to multiple stores,
    the images having a store configured with a volume type matching
    the image-volume's type will be migrated/associated to that store
    and their location url will be updated respectively to the new format
    i.e. cinder://store-id/volume-id
    If there is no store configured for the image, the location url will
    not be updated.
    """
    uri = loc['url']
    volume_id = loc['url'].split("/")[-1]
    scheme = urlparse.urlparse(uri).scheme
    location_map = store_api.location.SCHEME_TO_CLS_BACKEND_MAP
    if scheme not in location_map:
        LOG.warning(_LW("Unknown scheme '%(scheme)s' found in uri '%(uri)s'"),
                    {'scheme': scheme, 'uri': uri})
        return

    for store in location_map[scheme]:
        store_instance = location_map[scheme][store]['store']
        if store_instance.is_image_associated_with_store(context, volume_id):
            url_prefix = store_instance.url_prefix
            loc['url'] = "%s/%s" % (url_prefix, volume_id)
            loc['metadata']['store'] = "%s" % store
            return


def _update_s3_url(parsed, new_access_key, new_secret_key):
    """Update S3 URL with new credentials."""
    host_part = parsed.netloc.split('@')[-1]
    new_netloc = "%s:%s@%s" % (new_access_key, new_secret_key, host_part)
    # Rebuild URL with new credentials but keep all other parts same
    # We need to include params, query, fragment even if S3 URLs don't
    # use them. This is to make sure we don't lose any URL parts
    # when updating credentials
    return urlparse.urlunparse((
        parsed.scheme,
        new_netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment
    ))


def _get_store_credentials(store_instance):
    """Get credentials from store instance."""
    return (getattr(store_instance, 'access_key'),
            getattr(store_instance, 'secret_key'))


def _find_store_by_bucket(parsed_uri, location_map, scheme):
    """Find store instance by matching bucket from the URI."""
    # Extract bucket from url as our S3 URLs are
    # always in the format: s3://key:secret@host/bucket/object
    bucket_name = parsed_uri.path.strip('/').split('/')[0]

    # Find store that matches this bucket
    for store_name, store_info in location_map[scheme].items():
        store_instance = store_info['store']
        if store_instance.bucket == bucket_name:
            return (store_name, store_instance)


def _construct_s3_url(store_instance, scheme, path):
    """Construct the entire S3 URL including the object path."""
    access_key = getattr(store_instance, 'access_key')
    secret_key = getattr(store_instance, 'secret_key')
    s3_host = getattr(store_instance, 's3_host')
    bucket = getattr(store_instance, 'bucket')

    # Construct the full URL with the object path
    return "%s://%s:%s@%s/%s%s" % (
        scheme, access_key, secret_key, s3_host, bucket, path)


def _update_s3_location_and_store_id(context, loc):
    """Update S3 location and store ID for legacy images.

    :param context: The request context
    :param loc: The image location entry
    :returns: True if an update was made, False otherwise
    """
    uri = loc['url']
    parsed = urlparse.urlparse(uri)
    scheme = parsed.scheme

    location_map = store_api.location.SCHEME_TO_CLS_BACKEND_MAP
    if scheme not in location_map:
        LOG.debug("Unknown scheme '%(scheme)s' found in uri",
                  {'scheme': scheme})
        return False

    # URL format: s3://key:secret@host/bucket/object
    # Extract object path: everything after the bucket name
    object_path = parsed.path[parsed.path.find('/', 1):]
    # Extract image ID from object path
    image_id = object_path.split('/')[-1]

    # Get store name from metadata
    store_name = loc['metadata'].get('store')
    if store_name:
        # Multistore, find by store name
        store_instance = location_map[scheme][store_name]['store']
    else:
        # Old single store instance. Find by bucket and update store name
        store_result = _find_store_by_bucket(parsed, location_map, scheme)
        if store_result:
            store_name, store_instance = store_result
            loc['metadata']['store'] = store_name
        else:
            # No matching store found
            LOG.warning("No S3 store found for image %(image_id)s",
                        {'image_id': image_id})
            return False

    # For any store (old or new), update creds if there's a mismatch
    expected_url = _construct_s3_url(store_instance, scheme, object_path)
    if expected_url and loc['url'] != expected_url:
        LOG.info("S3 URL mismatch for image %(image_id)s, updating URL",
                 {'image_id': image_id})
        new_access_key, new_secret_key = _get_store_credentials(
            store_instance)
        loc['url'] = _update_s3_url(
            parsed, new_access_key, new_secret_key)
        return True

    return False


def get_updated_store_location(locations, context=None):
    for loc in locations:
        if loc['url'].startswith("cinder://") and context:
            _update_cinder_location_and_store_id(context, loc)
            continue

        store_id = _get_store_id_from_uri(loc['url'])
        if store_id:
            loc['metadata']['store'] = store_id

    return locations


def get_dir_separator():
    separator = ''
    staging_dir = "file://%s" % getattr(
        CONF, 'os_glance_staging_store').filesystem_store_datadir
    if not staging_dir.endswith('/'):
        separator = '/'
    return separator, staging_dir
