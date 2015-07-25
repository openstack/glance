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
import datetime
import traceback

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
import oslo_utils.importutils as imp
from oslo_utils import timeutils
import six
from webob import exc

from glance.common import client
from glance.common import exception
from glance.common import wsgi
from glance import i18n

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE


rpc_opts = [
    # NOTE(flaper87): Shamelessly copied
    # from oslo rpc.
    cfg.ListOpt('allowed_rpc_exception_modules',
                default=['glance.common.exception',
                         'exceptions',
                         ],
                help='Modules of exceptions that are permitted to be recreated'
                     ' upon receiving exception data from an rpc call.'),
]

CONF = cfg.CONF
CONF.register_opts(rpc_opts)


class RPCJSONSerializer(wsgi.JSONResponseSerializer):

    @staticmethod
    def _to_primitive(_type, _value):
        return {"_type": _type, "_value": _value}

    def _sanitizer(self, obj):
        if isinstance(obj, datetime.datetime):
            return self._to_primitive("datetime",
                                      obj.isoformat())

        return super(RPCJSONSerializer, self)._sanitizer(obj)


class RPCJSONDeserializer(wsgi.JSONRequestDeserializer):

    @staticmethod
    def _to_datetime(obj):
        return timeutils.normalize_time(timeutils.parse_isotime(obj))

    def _sanitizer(self, obj):
        try:
            _type, _value = obj["_type"], obj["_value"]
            return getattr(self, "_to_" + _type)(_value)
        except (KeyError, AttributeError):
            return obj


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
        :params filtered: List of methods that *can* be registered. Read
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

            if (not command or not isinstance(command, six.string_types) or
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
                    raise

                cls, val = e.__class__, encodeutils.exception_to_unicode(e)
                msg = (_LE("RPC Call Error: %(val)s\n%(tb)s") %
                       dict(val=val, tb=traceback.format_exc()))
                LOG.error(msg)

                # NOTE(flaper87): Don't propagate all exceptions
                # but the ones allowed by the user.
                module = cls.__module__
                if module not in CONF.allowed_rpc_exception_modules:
                    cls = exception.RPCError
                    val = six.text_type(exception.RPCError(cls=cls, val=val))

                cls_path = "%s.%s" % (cls.__module__, cls.__name__)
                result = {"_error": {"cls": cls_path, "val": val}}
            results.append(result)
        return results


class RPCClient(client.BaseClient):

    def __init__(self, *args, **kwargs):
        self._serializer = RPCJSONSerializer()
        self._deserializer = RPCJSONDeserializer()

        self.raise_exc = kwargs.pop("raise_exc", True)
        self.base_path = kwargs.pop("base_path", '/rpc')
        super(RPCClient, self).__init__(*args, **kwargs)

    @client.handle_unauthenticated
    def bulk_request(self, commands):
        """
        Execute multiple commands in a single request.

        :params commands: List of commands to send. Commands
        must respect the following form:

            {
                'command': 'method_name',
                'kwargs': method_kwargs
            }
        """
        body = self._serializer.to_json(commands)
        response = super(RPCClient, self).do_request('POST',
                                                     self.base_path,
                                                     body)
        return self._deserializer.from_json(response.read())

    def do_request(self, method, **kwargs):
        """
        Simple do_request override. This method serializes
        the outgoing body and builds the command that will
        be sent.

        :params method: The remote python method to call
        :params kwargs: Dynamic parameters that will be
            passed to the remote method.
        """
        content = self.bulk_request([{'command': method,
                                      'kwargs': kwargs}])

        # NOTE(flaper87): Return the first result if
        # a single command was executed.
        content = content[0]

        # NOTE(flaper87): Check if content is an error
        # and re-raise it if raise_exc is True. Before
        # checking if content contains the '_error' key,
        # verify if it is an instance of dict - since the
        # RPC call may have returned something different.
        if self.raise_exc and (isinstance(content, dict)
                               and '_error' in content):
            error = content['_error']
            try:
                exc_cls = imp.import_class(error['cls'])
                raise exc_cls(error['val'])
            except ImportError:
                # NOTE(flaper87): The exception
                # class couldn't be imported, using
                # a generic exception.
                raise exception.RPCError(**error)
        return content

    def __getattr__(self, item):
        """
        This method returns a method_proxy that
        will execute the rpc call in the registry
        service.
        """
        if item.startswith('_'):
            raise AttributeError(item)

        def method_proxy(**kw):
            return self.do_request(item, **kw)

        return method_proxy
