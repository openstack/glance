# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os
import sys

import glance_store
import jsonschema
from oslo_config import cfg
from oslo_serialization import jsonutils as json
from oslo_utils import encodeutils
from oslo_utils import excutils
import semantic_version
import six
import six.moves.urllib.parse as urlparse
import webob.exc

from glance.artifacts import gateway
from glance.artifacts import Showlevel
from glance.common.artifacts import loader
from glance.common.artifacts import serialization
from glance.common import exception
from glance.common import jsonpatchvalidator
from glance.common import utils
from glance.common import wsgi
import glance.db
from glance import i18n
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
_LE = i18n._LE
_ = i18n._

possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                                os.pardir,
                                                os.pardir))
if os.path.exists(os.path.join(possible_topdir, 'glance', '__init__.py')):
    sys.path.insert(0, possible_topdir)

CONF = cfg.CONF
CONF.import_group("profiler", "glance.common.wsgi")


class ArtifactsController(object):
    def __init__(self, db_api=None, store_api=None, plugins=None):
        self.db_api = db_api or glance.db.get_api()
        self.store_api = store_api or glance_store
        self.plugins = plugins or loader.ArtifactsPluginLoader(
            'glance.artifacts.types')
        self.gateway = gateway.Gateway(self.db_api,
                                       self.store_api, self.plugins)

    @staticmethod
    def _do_update_op(artifact, change):
        """Call corresponding method of the updater proxy.

        Here 'change' is a typical jsonpatch request dict:
            * 'path' - a json-pointer string;
            * 'op' - one of the allowed operation types;
            * 'value' - value to set (omitted when op = remove)
        """
        update_op = getattr(artifact, change['op'])
        update_op(change['path'], change.get('value'))
        return artifact

    @staticmethod
    def _get_artifact_with_dependencies(repo, art_id,
                                        type_name=None, type_version=None):
        """Retrieves an artifact with dependencies from db by its id.

        Show level is direct (only direct dependencies are shown).
        """
        return repo.get(art_id, show_level=Showlevel.DIRECT,
                        type_name=type_name, type_version=type_version)

    def show(self, req, type_name, type_version,
             show_level=Showlevel.TRANSITIVE, **kwargs):
        """Retrieves one artifact by id with its dependencies"""
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        try:
            art_id = kwargs.get('id')
            artifact = artifact_repo.get(art_id, type_name=type_name,
                                         type_version=type_version,
                                         show_level=show_level)
            return artifact
        except exception.ArtifactNotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)

    def list(self, req, type_name, type_version, state, **kwargs):
        """Retrieves a list of artifacts that match some params"""
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        filters = kwargs.pop('filters', {})

        filters.update(type_name={'value': type_name},
                       state={'value': state})
        if type_version is not None:
            filters['type_version'] = {'value': type_version}
        if 'version' in filters:
            for filter in filters['version']:
                if filter['value'] == 'latest':
                    if 'name' not in filters:
                        raise webob.exc.HTTPBadRequest(
                            'Filtering by latest version without specifying'
                            ' a name is not supported.')
                    filter['value'] = self._get_latest_version(
                        req, filters['name'][0]['value'], type_name,
                        type_version)

        res = artifact_repo.list(filters=filters,
                                 show_level=Showlevel.BASIC,
                                 **kwargs)
        result = {'artifacts': res}
        limit = kwargs.get("limit")
        if limit is not None and len(res) != 0 and len(res) == limit:
            result['next_marker'] = res[-1].id
        return result

    def _get_latest_version(self, req, name, type_name, type_version=None,
                            state='creating'):
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        filters = dict(name=[{"value": name}],
                       type_name={"value": type_name},
                       state={"value": state})
        if type_version is not None:
            filters["type_version"] = {"value": type_version}
        result = artifact_repo.list(filters=filters,
                                    show_level=Showlevel.NONE,
                                    sort_keys=[('version', None)])
        if len(result):
            return result[0].version

        msg = "No artifacts have been found"
        raise exception.ArtifactNotFound(message=msg)

    @utils.mutating
    def create(self, req, artifact_type, artifact_data, **kwargs):
        try:
            artifact_factory = self.gateway.get_artifact_type_factory(
                req.context, artifact_type)
            new_artifact = artifact_factory.new_artifact(**artifact_data)
            artifact_repo = self.gateway.get_artifact_repo(req.context)
            artifact_repo.add(new_artifact)
            # retrieve artifact from db
            return self._get_artifact_with_dependencies(artifact_repo,
                                                        new_artifact.id)
        except TypeError as e:
            raise webob.exc.HTTPBadRequest(explanation=e)
        except exception.ArtifactNotFound as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.DuplicateLocation as dup:
            raise webob.exc.HTTPBadRequest(explanation=dup.msg)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.InvalidParameterValue as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.LimitExceeded as e:
            raise webob.exc.HTTPRequestEntityTooLarge(
                explanation=e.msg, request=req, content_type='text/plain')
        except exception.Duplicate as dupex:
            raise webob.exc.HTTPConflict(explanation=dupex.msg)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

    @utils.mutating
    def update_property(self, req, id, type_name, type_version, path, data,
                        **kwargs):
        """Updates a single property specified by request url."""
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        try:
            artifact = self._get_artifact_with_dependencies(artifact_repo, id,
                                                            type_name,
                                                            type_version)
            self._ensure_write_access(artifact, req.context)
            # use updater mixin to perform updates: generate update path
            if req.method == "PUT":
                # replaces existing value or creates a new one
                if getattr(artifact, kwargs["attr"]):
                    artifact.replace(path=path, value=data)
                else:
                    artifact.add(path=path, value=data)
            else:
                # append to an existing value or create a new one
                artifact.add(path=path, value=data)
            artifact_repo.save(artifact)
            return self._get_artifact_with_dependencies(artifact_repo, id)
        except (exception.InvalidArtifactPropertyValue,
                exception.ArtifactInvalidProperty,
                exception.InvalidJsonPatchPath) as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

    @utils.mutating
    def update(self, req, id, type_name, type_version, changes, **kwargs):
        """Performs an update via json patch request"""
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        try:
            artifact = self._get_artifact_with_dependencies(artifact_repo, id,
                                                            type_name,
                                                            type_version)
            self._ensure_write_access(artifact, req.context)
            updated = artifact
            for change in changes:
                updated = self._do_update_op(updated, change)
            artifact_repo.save(updated)
            return self._get_artifact_with_dependencies(artifact_repo, id)
        except (exception.InvalidArtifactPropertyValue,
                exception.InvalidJsonPatchPath,
                exception.InvalidParameterValue) as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.StorageQuotaFull as e:
            msg = (_("Denying attempt to upload artifact because it exceeds "
                     "the quota: %s") % encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPRequestEntityTooLarge(
                explanation=msg, request=req, content_type='text/plain')
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.LimitExceeded as e:
            raise webob.exc.HTTPRequestEntityTooLarge(
                explanation=e.msg, request=req, content_type='text/plain')
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

    @utils.mutating
    def delete(self, req, id, type_name, type_version, **kwargs):
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        try:
            artifact = self._get_artifact_with_dependencies(
                artifact_repo, id, type_name=type_name,
                type_version=type_version)
            self._ensure_write_access(artifact, req.context)
            artifact_repo.remove(artifact)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except (glance_store.Forbidden, exception.Forbidden) as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except (glance_store.NotFound, exception.NotFound) as e:
            msg = (_("Failed to find artifact %(artifact_id)s to delete") %
                   {'artifact_id': id})
            raise webob.exc.HTTPNotFound(explanation=msg)
        except glance_store.exceptions.InUseByStore as e:
            msg = (_("Artifact %s could not be deleted "
                     "because it is in use: %s") % (id, e.msg))  # noqa
            raise webob.exc.HTTPConflict(explanation=msg)
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

    @utils.mutating
    def publish(self, req, id, type_name, type_version, **kwargs):
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        try:
            artifact = self._get_artifact_with_dependencies(
                artifact_repo, id, type_name=type_name,
                type_version=type_version)
            self._ensure_write_access(artifact, req.context)
            return artifact_repo.publish(artifact, context=req.context)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)
        except exception.NotAuthenticated as e:
            raise webob.exc.HTTPUnauthorized(explanation=e.msg)

    def _upload_list_property(self, method, blob_list, index, data, size):
        if method == 'PUT' and not index and len(blob_list) > 0:
            # PUT replaces everything, so PUT to non-empty collection is
            # forbidden
            raise webob.exc.HTTPMethodNotAllowed(
                explanation=_("Unable to PUT to non-empty collection"))
        if index is not None and index > len(blob_list):
            raise webob.exc.HTTPBadRequest(
                explanation=_("Index is out of range"))
        if index is None:
            # both POST and PUT create a new blob list
            blob_list.append((data, size))
        elif method == 'POST':
            blob_list.insert(index, (data, size))
        else:
            blob_list[index] = (data, size)

    @utils.mutating
    def upload(self, req, id, type_name, type_version, attr, size, data,
               index, **kwargs):
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        artifact = None
        try:
            artifact = self._get_artifact_with_dependencies(artifact_repo,
                                                            id,
                                                            type_name,
                                                            type_version)
            self._ensure_write_access(artifact, req.context)
            blob_prop = artifact.metadata.attributes.blobs.get(attr)
            if blob_prop is None:
                raise webob.exc.HTTPBadRequest(
                    explanation=_("Not a blob property '%s'") % attr)
            if isinstance(blob_prop, list):
                blob_list = getattr(artifact, attr)
                self._upload_list_property(req.method, blob_list,
                                           index, data, size)
            else:
                if index is not None:
                    raise webob.exc.HTTPBadRequest(
                        explanation=_("Not a list property '%s'") % attr)
                setattr(artifact, attr, (data, size))
            artifact_repo.save(artifact)
            return artifact

        except ValueError as e:
            exc_message = encodeutils.exception_to_unicode(e)
            LOG.debug("Cannot save data for artifact %(id)s: %(e)s",
                      {'id': id, 'e': exc_message})
            self._restore(artifact_repo, artifact)
            raise webob.exc.HTTPBadRequest(
                explanation=exc_message)

        except glance_store.StoreAddDisabled:
            msg = _("Error in store configuration. Adding artifacts to store "
                    "is disabled.")
            LOG.exception(msg)
            self._restore(artifact_repo, artifact)
            raise webob.exc.HTTPGone(explanation=msg, request=req,
                                     content_type='text/plain')

        except (glance_store.Duplicate,
                exception.InvalidImageStatusTransition) as e:
            LOG.exception(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPConflict(explanation=e.msg, request=req)

        except exception.Forbidden as e:
            msg = ("Not allowed to upload data for artifact %s" %
                   id)
            LOG.debug(msg)
            raise webob.exc.HTTPForbidden(explanation=msg, request=req)

        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)

        except glance_store.StorageFull as e:
            msg = _("Artifact storage media "
                    "is full: %s") % encodeutils.exception_to_unicode(e)
            LOG.error(msg)
            self._restore(artifact_repo, artifact)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                      request=req)

        except exception.StorageQuotaFull as e:
            msg = _("Artifact exceeds the storage "
                    "quota: %s") % encodeutils.exception_to_unicode(e)
            LOG.error(msg)
            self._restore(artifact_repo, artifact)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                      request=req)

        except exception.ImageSizeLimitExceeded as e:
            msg = _("The incoming artifact blob is "
                    "too large: %s") % encodeutils.exception_to_unicode(e)
            LOG.error(msg)
            self._restore(artifact_repo, artifact)
            raise webob.exc.HTTPRequestEntityTooLarge(explanation=msg,
                                                      request=req)

        except glance_store.StorageWriteDenied as e:
            msg = _("Insufficient permissions on artifact "
                    "storage media: %s") % encodeutils.exception_to_unicode(e)
            LOG.error(msg)
            self._restore(artifact_repo, artifact)
            raise webob.exc.HTTPServiceUnavailable(explanation=msg,
                                                   request=req)

        except webob.exc.HTTPGone as e:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE("Failed to upload artifact blob data due to"
                              " HTTP error"))

        except webob.exc.HTTPError as e:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE("Failed to upload artifact blob data due to HTTP"
                              " error"))
                self._restore(artifact_repo, artifact)

        except Exception as e:
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("Failed to upload artifact blob data due to "
                                  "internal error"))
                self._restore(artifact_repo, artifact)

    def download(self, req, id, type_name, type_version, attr, index,
                 **kwargs):
        artifact_repo = self.gateway.get_artifact_repo(req.context)
        try:
            artifact = artifact_repo.get(id, type_name, type_version)
            if attr in artifact.metadata.attributes.blobs:
                if isinstance(artifact.metadata.attributes.blobs[attr], list):
                    if index is None:
                        raise webob.exc.HTTPBadRequest(
                            explanation=_("Index is required"))
                    blob_list = getattr(artifact, attr)
                    try:
                        return blob_list[index]
                    except IndexError as e:
                        raise webob.exc.HTTPBadRequest(explanation=e.message)
                else:
                    if index is not None:
                        raise webob.exc.HTTPBadRequest(_("Not a list "
                                                         "property"))
                    return getattr(artifact, attr)
            else:
                message = _("Not a downloadable entity")
                raise webob.exc.HTTPBadRequest(explanation=message)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except (glance_store.NotFound, exception.NotFound) as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except (glance_store.Invalid, exception.Invalid) as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)

    def _restore(self, artifact_repo, artifact):
        """Restore the artifact to queued status.

        :param artifact_repo: The instance of ArtifactRepo
        :param artifact: The artifact will be restored
        """
        try:
            if artifact_repo and artifact:
                artifact.state = 'creating'
                artifact_repo.save(artifact)
        except Exception as e:
            msg = (_LE("Unable to restore artifact %(artifact_id)s: %(e)s") %
                   {'artifact_id': artifact.id,
                    'e': encodeutils.exception_to_unicode(e)})
            LOG.exception(msg)

    def list_artifact_types(self, req):
        plugins = self.plugins.plugin_map
        response = []
        base_link = "%s/v3/artifacts" % (CONF.public_endpoint or req.host_url)

        for type_name, plugin in six.iteritems(plugins.get("by_typename")):

            metadata = dict(
                type_name=type_name,
                displayed_name=plugin[0].metadata.type_display_name,
                versions=[]
            )

            for version in plugin:
                endpoint = version.metadata.endpoint
                type_version = "v" + version.metadata.type_version
                version_metadata = dict(
                    id=type_version,
                    link="%s/%s/%s" % (base_link, endpoint, type_version)
                )
                type_description = version.metadata.type_description
                if type_description is not None:
                    version_metadata['description'] = type_description
                metadata['versions'].append(version_metadata)
            response.append(metadata)

        return {"artifact_types": response}

    @staticmethod
    def _ensure_write_access(artifact, context):
        if context.is_admin:
            return
        if context.owner is None or context.owner != artifact.owner:
            raise exception.ArtifactForbidden(id=artifact.id)


class RequestDeserializer(wsgi.JSONRequestDeserializer,
                          jsonpatchvalidator.JsonPatchValidatorMixin):
    _available_sort_keys = ('name', 'status', 'container_format',
                            'disk_format', 'size', 'id', 'created_at',
                            'updated_at', 'version')
    _default_sort_dir = 'desc'

    _max_limit_number = 1000

    def __init__(self, schema=None, plugins=None):
        super(RequestDeserializer, self).__init__(
            methods_allowed=["replace", "remove", "add"])
        self.plugins = plugins or loader.ArtifactsPluginLoader(
            'glance.artifacts.types')

    def _validate_show_level(self, show_level):
        try:
            return Showlevel.from_str(show_level.strip().lower())
        except exception.ArtifactUnsupportedShowLevel as e:
            raise webob.exc.HTTPBadRequest(explanation=e.message)

    def show(self, req):
        res = self._process_type_from_request(req, True)
        params = req.params.copy()
        show_level = params.pop('show_level', None)
        if show_level is not None:
            res['show_level'] = self._validate_show_level(show_level)
        return res

    def _get_request_body(self, req):
        output = super(RequestDeserializer, self).default(req)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    def validate_body(self, request):
        try:
            body = self._get_request_body(request)
            return super(RequestDeserializer, self).validate_body(body)
        except exception.JsonPatchException as e:
            raise webob.exc.HTTPBadRequest(explanation=e)

    def default(self, request):
        return self._process_type_from_request(request)

    def _check_type_version(self, type_version):
        try:
            semantic_version.Version(type_version, partial=True)
        except ValueError as e:
            raise webob.exc.HTTPBadRequest(explanation=e)

    def _process_type_from_request(self, req,
                                   allow_implicit_version=False):
        try:
            type_name = req.urlvars.get('type_name')
            type_version = req.urlvars.get('type_version')
            if type_version is not None:
                self._check_type_version(type_version)
            # Even if the type_version is not specified and
            # 'allow_implicit_version' is False, this call is still needed to
            # ensure that at least one version of this type exists.
            artifact_type = self.plugins.get_class_by_endpoint(type_name,
                                                               type_version)
            res = {
                'type_name': artifact_type.metadata.type_name,
                'type_version':
                    artifact_type.metadata.type_version
                    if type_version is not None else None
            }
            if allow_implicit_version:
                res['artifact_type'] = artifact_type
            return res

        except exception.ArtifactPluginNotFound as e:
            raise webob.exc.HTTPBadRequest(explanation=e.msg)

    def create(self, req):
        res = self._process_type_from_request(req, True)
        res["artifact_data"] = self._get_request_body(req)
        return res

    def update(self, req):
        res = self._process_type_from_request(req)
        res["changes"] = self.validate_body(req)
        return res

    def update_property(self, req):
        """Data is expected in form {'data': ...}"""
        res = self._process_type_from_request(req)
        data_schema = {
            "type": "object",
            "properties": {"data": {}},
            "required": ["data"],
            "$schema": "http://json-schema.org/draft-04/schema#"}
        try:
            json_body = json.loads(req.body)
            jsonschema.validate(json_body, data_schema)
            # TODO(ivasilevskaya):
            # by now the deepest nesting level == 1 (ex. some_list/3),
            # has to be fixed for dict properties
            attr = req.urlvars["attr"]
            path_left = req.urlvars["path_left"]
            path = (attr if not path_left
                    else "%(attr)s/%(path_left)s" % {'attr': attr,
                                                     'path_left': path_left})
            res.update(data=json_body["data"], path=path)
            return res
        except (ValueError, jsonschema.ValidationError) as e:
            msg = _("Invalid json body: %s") % e.message
            raise webob.exc.HTTPBadRequest(explanation=msg)

    def upload(self, req):
        res = self._process_type_from_request(req)
        index = req.urlvars.get('path_left')
        try:
            # for blobs only one level of indexing is supported
            # (ex. bloblist/0)
            if index is not None:
                index = int(index)
        except ValueError:
            msg = _("Only list indexes are allowed for blob lists")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        artifact_size = req.content_length or None
        res.update(size=artifact_size, data=req.body_file,
                   index=index)
        return res

    def download(self, req):
        res = self._process_type_from_request(req)
        index = req.urlvars.get('index')
        if index is not None:
            index = int(index)
        res.update(index=index)
        return res

    def _validate_limit(self, limit):
        if limit is None:
            return self._max_limit_number
        try:
            limit = int(limit)
        except ValueError:
            msg = _("Limit param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit < 0:
            msg = _("Limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit > self._max_limit_number:
            msg = _("Limit param"
                    " must not be higher than %d") % self._max_limit_number
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

    def _validate_sort_key(self, sort_key, artifact_type, type_version=None):
        if sort_key in self._available_sort_keys:
            return sort_key, None
        elif type_version is None:
            msg = (_('Invalid sort key: %(sort_key)s. '
                     'If type version is not set it must be one of'
                     ' the following: %(available)s.') %
                   {'sort_key': sort_key,
                    'available': ', '.join(self._available_sort_keys)})
            raise webob.exc.HTTPBadRequest(explanation=msg)
        prop_type = artifact_type.metadata.attributes.all.get(sort_key)
        if prop_type is None or prop_type.DB_TYPE not in ['string',
                                                          'numeric',
                                                          'int',
                                                          'bool']:
            msg = (_('Invalid sort key: %(sort_key)s. '
                     'You cannot sort by this property') %
                   {'sort_key': sort_key})
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_key, prop_type.DB_TYPE

    def _validate_sort_dir(self, sort_dir):
        if sort_dir not in ['asc', 'desc']:
            msg = _('Invalid sort direction: %s') % sort_dir
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return sort_dir

    def _get_sorting_params(self, params, artifact_type, type_version=None):

        sort_keys = []
        sort_dirs = []

        if 'sort' in params:
            for sort_param in params.pop('sort').strip().split(','):
                key, _sep, dir = sort_param.partition(':')
                if not dir:
                    dir = self._default_sort_dir
                sort_keys.append(self._validate_sort_key(key.strip(),
                                                         artifact_type,
                                                         type_version))
                sort_dirs.append(self._validate_sort_dir(dir.strip()))

        if not sort_keys:
            sort_keys = [('created_at', None)]
        if not sort_dirs:
            sort_dirs = [self._default_sort_dir]

        return sort_keys, sort_dirs

    def _bring_to_type(self, type_name, value):
        mapper = {'int': int,
                  'string': str,
                  'text': str,
                  'bool': bool,
                  'numeric': float}
        return mapper[type_name](value)

    def _get_filters(self, artifact_type, params):
        error_msg = 'Unexpected filter property'
        filters = dict()
        for filter, raw_value in params.items():

            # first, get the comparison operator
            left, sep, right = raw_value.strip().partition(':')
            if not sep:
                op = "default"
                value = left.strip()
            else:
                op = left.strip().upper()
                value = right.strip()

            # then, understand what's the property to filter and its value
            if '.' in filter:  # Indicates a dict-valued property with a key
                prop_name, key = filter.split('.', 1)
            else:
                prop_name = filter
                key = None
            prop_type = artifact_type.metadata.attributes.all.get(prop_name)
            if prop_type is None:
                raise webob.exc.HTTPBadRequest(error_msg)
            key_only_check = False
            position = None
            if isinstance(prop_type, dict):
                if key is None:
                    key = value
                    val = None
                    key_only_check = True
                else:
                    val = value

                if isinstance(prop_type.properties, dict):
                    # This one is to handle the case of composite dict, having
                    # different types of values at different keys, i.e. object
                    prop_type = prop_type.properties.get(key)
                    if prop_type is None:
                        raise webob.exc.HTTPBadRequest(error_msg)
                else:
                    prop_type = prop_type.properties

                property_name = prop_name + '.' + key
                property_value = val
            else:
                if key is not None:
                    raise webob.exc.HTTPBadRequest(error_msg)
                property_name = prop_name
                property_value = value

            # now detect the value DB type
            if prop_type.DB_TYPE is not None:
                str_type = prop_type.DB_TYPE
            elif isinstance(prop_type, list):
                if not isinstance(prop_type.item_type, list):
                    position = "any"
                    str_type = prop_type.item_type.DB_TYPE
                else:
                    raise webob.exc.HTTPBadRequest('Filtering by tuple-like'
                                                   ' fields is not supported')
            else:
                raise webob.exc.HTTPBadRequest(error_msg)
            if property_value is not None:
                property_value = self._bring_to_type(str_type, property_value)

            # convert the default operation to NE, EQ or IN
            if key_only_check:
                if op == 'default':
                    op = 'NE'
                else:
                    raise webob.exc.HTTPBadRequest('Comparison not supported '
                                                   'for key-only filtering')
            else:
                if op == 'default':
                    op = 'IN' if isinstance(prop_type, list) else 'EQ'

            filters.setdefault(property_name, [])

            filters[property_name].append(dict(operator=op, position=position,
                                               value=property_value,
                                               type=str_type))
        return filters

    def list(self, req):
        res = self._process_type_from_request(req, True)
        params = req.params.copy()
        show_level = params.pop('show_level', None)
        if show_level is not None:
            res['show_level'] = self._validate_show_level(show_level.strip())

        limit = params.pop('limit', None)
        marker = params.pop('marker', None)

        query_params = dict()

        query_params['sort_keys'], query_params['sort_dirs'] = (
            self._get_sorting_params(params, res['artifact_type'],
                                     res['type_version']))

        if marker is not None:
            query_params['marker'] = marker

        query_params['limit'] = self._validate_limit(limit)

        query_params['filters'] = self._get_filters(res['artifact_type'],
                                                    params)

        query_params['type_name'] = res['artifact_type'].metadata.type_name

        return query_params

    def list_artifact_types(self, req):
        return {}


class ResponseSerializer(wsgi.JSONResponseSerializer):
    # TODO(ivasilevskaya): ideally this should be autogenerated/loaded
    ARTIFACTS_ENDPOINT = '/v3/artifacts'
    fields = ['id', 'name', 'version', 'type_name', 'type_version',
              'visibility', 'state', 'owner', 'scope', 'created_at',
              'updated_at', 'tags', 'dependencies', 'blobs', 'properties']

    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()

    def default(self, response, res):
        artifact = serialization.serialize_for_client(
            res, show_level=Showlevel.DIRECT)
        body = json.dumps(artifact, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def create(self, response, artifact):
        response.status_int = 201
        self.default(response, artifact)
        response.location = (
            '%(root_url)s/%(type_name)s/v%(type_version)s/%(id)s' % dict(
                root_url=ResponseSerializer.ARTIFACTS_ENDPOINT,
                type_name=artifact.metadata.endpoint,
                type_version=artifact.metadata.type_version,
                id=artifact.id))

    def list(self, response, res):
        params = dict(response.request.params)
        params.pop('marker', None)
        query = urlparse.urlencode(params)
        type_name = response.request.urlvars.get('type_name')
        type_version = response.request.urlvars.get('type_version')
        if response.request.urlvars.get('state') == 'creating':
            drafts = "/drafts"
        else:
            drafts = ""

        artifacts_list = [
            serialization.serialize_for_client(a, show_level=Showlevel.NONE)
            for a in res['artifacts']]
        url = "/v3/artifacts"
        if type_name:
            url += "/" + type_name
        if type_version:
            url += "/v" + type_version
        url += drafts
        if query:
            first_url = url + "?" + query
        else:
            first_url = url
        body = {
            "artifacts": artifacts_list,
            "first": first_url
        }
        if 'next_marker' in res:
            params['marker'] = res['next_marker']
            next_query = urlparse.urlencode(params)
            body['next'] = url + '?' + next_query
        content = json.dumps(body, ensure_ascii=False)
        response.unicode_body = six.text_type(content)
        response.content_type = 'application/json'

    def delete(self, response, result):
        response.status_int = 204

    def download(self, response, blob):
        response.headers['Content-Type'] = 'application/octet-stream'
        response.app_iter = iter(blob.data_stream)
        if blob.checksum:
            response.headers['Content-MD5'] = blob.checksum
        response.headers['Content-Length'] = str(blob.size)

    def list_artifact_types(self, response, res):
        body = json.dumps(res, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'


def create_resource():
    """Images resource factory method"""
    plugins = loader.ArtifactsPluginLoader('glance.artifacts.types')
    deserializer = RequestDeserializer(plugins=plugins)
    serializer = ResponseSerializer()
    controller = ArtifactsController(plugins=plugins)
    return wsgi.Resource(controller, deserializer, serializer)
