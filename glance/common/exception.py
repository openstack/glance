# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""Glance exception subclasses"""

import urlparse


class RedirectException(Exception):
    def __init__(self, url):
        self.url = urlparse.urlparse(url)


class GlanceException(Exception):
    """
    Base Glance Exception

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.
    """
    message = _("An unknown exception occurred")

    def __init__(self, message=None, *args, **kwargs):
        if not message:
            message = self.message
        try:
            message = message % kwargs
        except Exception:
            # at least get the core message out if something happened
            pass
        super(GlanceException, self).__init__(message)


class MissingArgumentError(GlanceException):
    message = _("Missing required argument.")


class MissingCredentialError(GlanceException):
    message = _("Missing required credential: %(required)s")


class BadAuthStrategy(GlanceException):
    message = _("Incorrect auth strategy, expected \"%(expected)s\" but "
                "received \"%(received)s\"")


class NotFound(GlanceException):
    message = _("An object with the specified identifier was not found.")


class UnknownScheme(GlanceException):
    message = _("Unknown scheme '%(scheme)s' found in URI")


class BadStoreUri(GlanceException):
    message = _("The Store URI was malformed.")


class Duplicate(GlanceException):
    message = _("An object with the same identifier already exists.")


class StorageFull(GlanceException):
    message = _("There is not enough disk space on the image storage media.")


class StorageWriteDenied(GlanceException):
    message = _("Permission to write image storage media denied.")


class AuthBadRequest(GlanceException):
    message = _("Connect error/bad request to Auth service at URL %(url)s.")


class AuthUrlNotFound(GlanceException):
    message = _("Auth service at URL %(url)s not found.")


class AuthorizationFailure(GlanceException):
    message = _("Authorization failed.")


class NotAuthenticated(GlanceException):
    message = _("You are not authenticated.")


class Forbidden(GlanceException):
    message = _("You are not authorized to complete this action.")


class ForbiddenPublicImage(Forbidden):
    message = _("You are not authorized to complete this action.")


#NOTE(bcwaldon): here for backwards-compatability, need to deprecate.
class NotAuthorized(Forbidden):
    message = _("You are not authorized to complete this action.")


class Invalid(GlanceException):
    message = _("Data supplied was not valid.")


class InvalidSortKey(Invalid):
    message = _("Sort key supplied was not valid.")


class InvalidFilterRangeValue(Invalid):
    message = _("Unable to filter using the specified range.")


class AuthorizationRedirect(GlanceException):
    message = _("Redirecting to %(uri)s for authorization.")


class DatabaseMigrationError(GlanceException):
    message = _("There was an error migrating the database.")


class ClientConnectionError(GlanceException):
    message = _("There was an error connecting to a server")


class ClientConfigurationError(GlanceException):
    message = _("There was an error configuring the client.")


class MultipleChoices(GlanceException):
    message = _("The request returned a 302 Multiple Choices. This generally "
                "means that you have not included a version indicator in a "
                "request URI.\n\nThe body of response returned:\n%(body)s")


class LimitExceeded(GlanceException):
    message = _("The request returned a 413 Request Entity Too Large. This "
                "generally means that rate limiting or a quota threshold was "
                "breached.\n\nThe response body:\n%(body)s")

    def __init__(self, *args, **kwargs):
        self.retry_after = (int(kwargs['retry']) if kwargs.get('retry')
                            else None)
        super(LimitExceeded, self).__init__(*args, **kwargs)


class ServiceUnavailable(GlanceException):
    message = _("The request returned 503 Service Unavilable. This "
                "generally occurs on service overload or other transient "
                "outage.")

    def __init__(self, *args, **kwargs):
        self.retry_after = (int(kwargs['retry']) if kwargs.get('retry')
                            else None)
        super(ServiceUnavailable, self).__init__(*args, **kwargs)


class ServerError(GlanceException):
    message = _("The request returned 500 Internal Server Error.")


class UnexpectedStatus(GlanceException):
    message = _("The request returned an unexpected status: %(status)s."
                "\n\nThe response body:\n%(body)s")


class InvalidContentType(GlanceException):
    message = _("Invalid content type %(content_type)s")


class BadRegistryConnectionConfiguration(GlanceException):
    message = _("Registry was not configured correctly on API server. "
                "Reason: %(reason)s")


class BadStoreConfiguration(GlanceException):
    message = _("Store %(store_name)s could not be configured correctly. "
               "Reason: %(reason)s")


class BadDriverConfiguration(GlanceException):
    message = _("Driver %(driver_name)s could not be configured correctly. "
               "Reason: %(reason)s")


class StoreDeleteNotSupported(GlanceException):
    message = _("Deleting images from this store is not supported.")


class StoreAddDisabled(GlanceException):
    message = _("Configuration for store failed. Adding images to this "
               "store is disabled.")


class InvalidNotifierStrategy(GlanceException):
    message = _("'%(strategy)s' is not an available notifier strategy.")


class MaxRedirectsExceeded(GlanceException):
    message = _("Maximum redirects (%(redirects)s) was exceeded.")


class InvalidRedirect(GlanceException):
    message = _("Received invalid HTTP redirect.")


class NoServiceEndpoint(GlanceException):
    message = _("Response from Keystone does not contain a Glance endpoint.")


class RegionAmbiguity(GlanceException):
    message = _("Multiple 'image' service matches for region %(region)s. This "
                "generally means that a region is required and you have not "
                "supplied one.")


class WorkerCreationFailure(GlanceException):
    message = _("Server worker creation failed: %(reason)s.")


class SchemaLoadError(GlanceException):
    message = _("Unable to load schema: %(reason)s")


class InvalidObject(GlanceException):
    message = _("Provided object does not match schema "
                "'%(schema)s': %(reason)s")


class UnsupportedHeaderFeature(GlanceException):
    message = _("Provided header feature is unsupported: %(feature)s")


class InUseByStore(GlanceException):
    message = _("The image cannot be deleted because it is in use through "
                "the backend store outside of Glance.")


class ImageSizeLimitExceeded(GlanceException):
    message = _("The provided image is too large.")
