# Copyright 2021 Red Hat, Inc.
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

from oslo_config import cfg
from oslo_limit import exception as ol_exc
from oslo_limit import limit
from oslo_log import log as logging
from oslo_utils import units

from glance.common import exception
from glance.db.sqlalchemy import api as db
from glance.i18n import _LE

CONF = cfg.CONF
CONF.import_opt('use_keystone_limits', 'glance.common.config')
LOG = logging.getLogger(__name__)
limit.opts.register_opts(CONF)

QUOTA_IMAGE_SIZE_TOTAL = 'image_size_total'
QUOTA_IMAGE_STAGING_TOTAL = 'image_stage_total'
QUOTA_IMAGE_COUNT_TOTAL = 'image_count_total'
QUOTA_IMAGE_COUNT_UPLOADING = 'image_count_uploading'


def _enforce_some(context, project_id, quota_value_fns, deltas):
    """Helper method to enforce a set of quota values.

    :param context: The RequestContext
    :param project_id: The project_id of the tenant being checked
    :param get_value_fns: A mapping of quota names to functions that will be
                          called with no arguments to return the numerical
                          value representing current usage.
    :param deltas: A mapping of quota names to the amount of resource being
                   requested for each (to be added to the current usage before
                   determining if over-quota).
    :raises: exception.LimitExceeded if the current usage is over the defined
             limit.
    :returns: None if the tenant is not currently over their quota.
    """
    if not CONF.use_keystone_limits:
        return

    def callback(project_id, resource_names):
        return {name: quota_value_fns[name]()
                for name in resource_names}

    enforcer = limit.Enforcer(callback)
    try:
        enforcer.enforce(project_id,
                         {quota_name: deltas.get(quota_name, 0)
                          for quota_name in quota_value_fns})
    except ol_exc.ProjectOverLimit as e:
        raise exception.LimitExceeded(body=str(e))
    except ol_exc.SessionInitError as e:
        LOG.error(_LE('Failed to initialize oslo_limit, likely due to '
                      'incorrect or insufficient configuration: %(err)s'),
                  {'err': str(e)})
        # We could just raise LimitExceeded here, but a 500 is
        # appropriate for incorrect server-side configuration, so we
        # re-raise here after the above error message to make sure we
        # are noticed.
        raise


def _enforce_one(context, project_id, quota_name, get_value_fn, delta=0):
    """Helper method to enforce a single named quota value.

    :param context: The RequestContext
    :param project_id: The project_id of the tenant being checked
    :param quota_name: One of the quota names defined above
    :param get_value_fn: A function that will be called with no arguments to
                         return the numerical value representing current usage.
    :param delta: The amount of resource being requested (to be added to the
                  current usage before determining if over-quota).
    :raises: exception.LimitExceeded if the current usage is over the defined
             limit.
    :returns: None if the tenant is not currently over their quota.
    """

    return _enforce_some(context, project_id,
                         {quota_name: get_value_fn},
                         {quota_name: delta})


def enforce_image_size_total(context, project_id, delta=0):
    """Enforce the image_size_total quota.

    This enforces the total image size quota for the supplied project_id.
    """
    _enforce_one(
        context, project_id, QUOTA_IMAGE_SIZE_TOTAL,
        lambda: db.user_get_storage_usage(context, project_id) // units.Mi,
        delta=delta)


def enforce_image_staging_total(context, project_id, delta=0):
    """Enforce the image_stage_total quota.

    This enforces the total size of all images stored in staging areas
    for the supplied project_id.
    """
    _enforce_one(
        context, project_id, QUOTA_IMAGE_STAGING_TOTAL,
        lambda: db.user_get_staging_usage(context, project_id) // units.Mi,
        delta=delta)


def enforce_image_count_total(context, project_id):
    """Enforce the image_count_total quota.

    This enforces the total count of non-deleted images owned by the
    supplied project_id.
    """
    _enforce_one(
        context, project_id, QUOTA_IMAGE_COUNT_TOTAL,
        lambda: db.user_get_image_count(context, project_id),
        delta=1)


def enforce_image_count_uploading(context, project_id):
    """Enforce the image_count_uploading quota.

    This enforces the total count of images in any state of upload by
    the supplied project_id.

    :param delta: This defaults to one, but should be zero when checking
                  an operation on an image that already counts against this
                  quota (i.e. a stage operation of an existing queue image).
    """
    _enforce_one(
        context, project_id, QUOTA_IMAGE_COUNT_UPLOADING,
        lambda: db.user_get_uploading_count(context, project_id),
        delta=0)


def get_usage(context, project_id=None):
    if not CONF.use_keystone_limits:
        return {}

    if not project_id:
        project_id = context.project_id

    usages = {
        QUOTA_IMAGE_SIZE_TOTAL: lambda: db.user_get_storage_usage(
            context, project_id) // units.Mi,
        QUOTA_IMAGE_STAGING_TOTAL: lambda: db.user_get_staging_usage(
            context, project_id) // units.Mi,
        QUOTA_IMAGE_COUNT_TOTAL: lambda: db.user_get_image_count(
            context, project_id),
        QUOTA_IMAGE_COUNT_UPLOADING: lambda: db.user_get_uploading_count(
            context, project_id),
    }

    def callback(project_id, resource_names):
        return {name: usages[name]()
                for name in resource_names}

    enforcer = limit.Enforcer(callback)
    return enforcer.calculate_usage(project_id, list(usages.keys()))
