# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Red Hat, Inc.
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
RPC Controller
"""
import traceback

from oslo.config import cfg
from webob import exc

from glance.common import exception
import glance.openstack.common.log as logging


LOG = logging.getLogger(__name__)


rpc_opts = [
    # NOTE(flaper87): Shamelessly copied
    # from oslo rpc.
    cfg.ListOpt('allowed_rpc_exception_modules',
                default=['openstack.common.exception',
                         'glance.common.exception',
                         'exceptions',
                         ],
                help='Modules of exceptions that are permitted to be recreated'
                     'upon receiving exception data from an rpc call.'),
]

CONF = cfg.CONF
CONF.register_opts(rpc_opts)


class Controller(object):
    """
    Base RPCController.

    This is the base controller for RPC based APIs. Commands
    handled by this controller respect the following form:

        [{
            'command': 'method_name',
            'kwargs': {...}
        }]

    The controller is capable of processing more than one command
    per request and will always return a list of results.

    :params raise_exc: Boolean that specifies whether to raise
    exceptions instead of "serializing" them.
    """

    def __init__(self, raise_exc=False):
        self._registered = {}
        self.raise_exc = raise_exc

    def register(self, resource, filtered=None, excluded=None, refiner=None):
        """
        Exports methods through the RPC Api.

        :params resource: Resource's instance to register.
        :params filtered: List of methods that *can* me registered. Read
        as "Method must be in this list".
        :params excluded: List of methods to exclude.
        :params refiner: Callable to use as filter for methods.

        :raises AssertionError: If refiner is not callable.
        """

        funcs = filter(lambda x: not x.startswith("_"), dir(resource))

        if filtered:
            funcs = [f for f in funcs if f in filtered]

        if excluded:
            funcs = [f for f in funcs if f not in excluded]

        if refiner:
            assert callable(refiner), "Refiner must be callable"
            funcs = filter(refiner, funcs)

        for name in funcs:
            meth = getattr(resource, name)

            if not callable(meth):
                continue

            self._registered[name] = meth

    def __call__(self, req, body):
        """
        Executes the command
        """

        if not isinstance(body, list):
            msg = _("Request must be a list of commands")
            raise exc.HTTPBadRequest(explanation=msg)

        def validate(cmd):
            if not isinstance(cmd, dict):
                msg = _("Bad Command: %s") % str(cmd)
                raise exc.HTTPBadRequest(explanation=msg)

            command, kwargs = cmd.get("command"), cmd.get("kwargs")

            if (not command or not isinstance(command, basestring) or
                    (kwargs and not isinstance(kwargs, dict))):
                msg = _("Wrong command structure: %s") % (str(cmd))
                raise exc.HTTPBadRequest(explanation=msg)

            method = self._registered.get(command)
            if not method:
                # Just raise 404 if the user tries to
                # access a private method. No need for
                # 403 here since logically the command
                # is not registered to the rpc dispatcher
                raise exc.HTTPNotFound(explanation=_("Command not found"))

            return True

        # If more than one command were sent then they might
        # be intended to be executed sequentially, that for,
        # lets first verify they're all valid before executing
        # them.
        commands = filter(validate, body)

        results = []
        for cmd in commands:
            # kwargs is not required
            command, kwargs = cmd["command"], cmd.get("kwargs", {})
            method = self._registered[command]
            try:
                result = method(req.context, **kwargs)
            except Exception as e:
                if self.raise_exc:
                    raise e

                cls, val = e.__class__, str(e)
                msg = (_("RPC Call Error: %(val)s\n%(tb)s") %
                       dict(val=val, tb=traceback.format_exc()))
                LOG.error(msg)

                # NOTE(flaper87): Don't propagate all exceptions
                # but the ones allowed by the user.
                module = cls.__module__
                if module not in CONF.allowed_rpc_exception_modules:
                    cls = exception.RPCError
                    val = str(exception.RPCError(cls=cls, val=val))

                cls_path = "%s.%s" % (cls.__module__, cls.__name__)
                result = {"_error": {"cls": cls_path, "val": val}}
            results.append(result)
        return results
