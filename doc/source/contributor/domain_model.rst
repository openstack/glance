..
      Copyright 2015 OpenStack Foundation
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

============
Domain model
============

The main goal of a domain model is refactoring the logic around
object manipulation by splitting it to independent layers. Each
subsequent layer wraps the previous one creating an "onion" structure,
thus realizing a design pattern called "Decorator." The main feature
of domain model is to use a composition instead of inheritance or
basic decoration while building an architecture. This provides
flexibility and transparency of an internal organization for a developer,
because he does not know what layers are used and works with a domain
model object as with a common object.

Inner architecture
~~~~~~~~~~~~~~~~~~

Each layer defines its own operations' implementation through a
special ``proxy`` class. At first, operations are performed on the
upper layer, then they successively pass the control to the underlying
layers.

The nesting of layers can be specified explicitly using a programmer
interface Gateway or implicitly using ``helper`` classes. Nesting
may also depend on various conditions, skipping or adding additional
layers during domain object creation.

Proxies
~~~~~~~

The layer behavior is described in special ``proxy`` classes
that must provide exactly the same interface as the original class
does. In addition, each ``proxy`` class has a field ``base``
indicating a lower layer object that is an instance of another
``proxy`` or ``original`` class.

To access the rest of the fields, you can use special ``proxy``
properties or universal methods ``set_property`` and ``get_property``.

In addition, the ``proxy`` class must have an ``__init__`` format
method::

        def __init__(self, base, helper_class=None, helper_kwargs=None, **kwargs)

where ``base`` corresponds to the underlying object layer,
``proxy_class`` and ``proxy_kwargs`` are optional and are used to
create a ``helper`` class.
Thus, to access a ``meth1`` method from the underlying layer, it is
enough to call it on the ``base`` object::

        def meth1(*args, **kwargs):
                …
                self.base.meth1(*args, **kwargs)
                …

To get access to the domain object field, it is recommended to use
properties that are created by an auxiliary function::

        def _create_property_proxy(attr):
            def get_attr(self):
                return getattr(self.base, attr)

            def set_attr(self, value):
                return setattr(self.base, attr, value)

            def del_attr(self):
                return delattr(self.base, attr)

            return property(get_attr, set_attr, del_attr)

So, the reference to the underlying layer field ``prop1`` looks like::

        class Proxy(object):
                …
                prop1 = _create_property_proxy('prop1')
                …

If the number of layers is big, it is reasonable to create a common
parent ``proxy`` class that provides further control transfer. This
facilitates the writing of specific layers if they do not provide a
particular implementation of some operation.

Gateway
~~~~~~~

``gateway`` is a mechanism to explicitly specify a composition of
the domain model layers. It defines an interface to retrieve the
domain model object based on the ``proxy`` classes described above.

Example of the gateway implementation
-------------------------------------

This example defines three classes:

* ``Base`` is the main class that sets an interface for all the
  ``proxy`` classes.
* ``LoggerProxy`` class implements additional logic associated with
  the logging of messages from the ``print_msg`` method.
* ``ValidatorProxy`` class implements an optional check that helps to
  determine whether all the parameters in the ``sum_numbers`` method
  are positive.

::

 class Base(object):
     ""Base class in domain model."""
     msg = "Hello Domain"

     def print_msg(self):
         print(self.msg)

     def sum_numbers(self, *args):
         return sum(args)

 class LoggerProxy(object):
     """"Class extends functionality by writing message to log."""
     def __init__(self, base, logg):
         self.base = base
         self.logg = logg

     # Proxy to provide implicit access to inner layer.
     msg = _create_property_proxy('msg')

     def print_msg(self):
         # Write message to log and then pass the control to inner layer.
         self.logg.write("Message %s has been written to the log") % self.msg
         self.base.print_msg()

     def sum_numbers(self, *args):
         # Nothing to do here. Just pass the control to the next layer.
         return self.base.sum_numbers(*args)

 class ValidatorProxy(object):
     """Class validates that input parameters are correct."""
     def __init__(self, base):
         self.base = base

     msg = _create_property_proxy('msg')

     def print_msg(self):
         # There are no checks.
         self.base.print_msg()

     def sum_numbers(self, *args):
         # Validate input numbers and pass them further.
         for arg in args:
             if arg <= 0:
                 return "Only positive numbers are supported."
         return self.base.sum_numbers(*args)

Thus, the ``gateway`` method for the above example may look like:

::

   def gateway(logg, only_positive=True):
       base = Base()
       logger = LoggerProxy(base, logg)
       if only_positive:
           return ValidatorProxy(logger)
       return logger

   domain_object = gateway(sys.stdout, only_positive=True)

It is important to consider that the order of the layers matters.
And even if layers are logically independent from each other,
rearranging them in different order may lead to another result.

Helpers
~~~~~~~

``Helper`` objects are used for an implicit nesting assignment that
is based on a specification described in an auxiliary method (similar
to ``gateway``). This approach may be helpful when using a *simple
factory* for generating objects. Such a way is more flexible as it
allows specifying the wrappers dynamically.

The ``helper`` class is unique for all the ``proxy`` classes and it
has the following form:

::

   class Helper(object):
       def __init__(self, proxy_class=None, proxy_kwargs=None):
           self.proxy_class = proxy_class
           self.proxy_kwargs = proxy_kwargs or {}

       def proxy(self, obj):
           """Wrap an object."""
           if obj is None or self.proxy_class is None:
               return obj
           return self.proxy_class(obj, **self.proxy_kwargs)

       def unproxy(self, obj):
           """Return object from inner layer."""
           if obj is None or self.proxy_class is None:
               return obj
           return obj.base

Example of a simple factory implementation
------------------------------------------

Here is a code of a *simple factory* for generating objects from the
previous example. It specifies a ``BaseFactory`` class with a
``generate`` method and related ``proxy`` classes:

::

   class BaseFactory(object):
       """Simple factory to generate an object."""
       def generate(self):
           return Base()

   class LoggerFactory(object):
       """Proxy class to add logging functionality."""
       def __init__(self, base, logg, proxy_class=None, proxy_kwargs=None):
           self.helper = Helper(proxy_class, proxy_kwargs)
           self.base = base
           self.logg = logg

       def generate(self):
           return self.helper.proxy(self.base.generate())

   class ValidatorFactory(object):
       """Proxy class to add validation."""
       def __init__(self, base, only_positive=True, proxy_class=None, proxy_kwargs=None):
           self.helper = Helper(proxy_class, proxy_kwargs)
           self.base = base
           self.only_positive = only_positive

       def generate(self):
           if self.only_positive:
               # Wrap in ValidatorProxy if required.
               return self.helper.proxy(self.base.generate())
           return self.base.generate()

Further, ``BaseFactory`` and related ``proxy`` classes are combined
together:

::

   def create_factory(logg, only_positive=True):
       base_factory = BaseFactory()
       logger_factory = LoggerFactory(base_factory, logg,
                                      proxy_class=LoggerProxy,
                                      proxy_kwargs=dict(logg=logg))
       validator_factory = ValidatorFactory(logger_factory, only_positive,
                                            proxy_class = ValidatorProxy)
       return validator_factory

Ultimately, to generate a domain object, you create and run a factory
method ``generate`` which implicitly creates a composite object. This
method is based on specifications that are set forth in the ``proxy``
class.

::

   factory = create_factory(sys.stdout, only_positive=False)
   domain_object = factory.generate()

Why do you need a domain if you can use decorators?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the above examples, to implement the planned logic, it is quite
possible to use standard Python language techniques such as
decorators. However, to implement more complicated operations, the
domain model is reasonable and justified.

In general, the domain is useful when:

* there are more than three layers. In such case, the domain model
  usage facilitates the understanding and supporting of the code;
* wrapping must be implemented depending on some conditions,
  including dynamic wrapping;
* there is a requirement to wrap objects implicitly by helpers.
