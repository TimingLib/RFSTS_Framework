"""
This module is the center of all decorators.

Usually, services call the decorators as follows:

.. doctest::

    >>> from nicu.decor.info import deprecated
    >>> from nicu.decor.mode import synchronized

As more and more decorators added into :class:`nicu.decor` later, the
classification of decorators may change. So each decorator may be divided
into another file, which leds to modify the code related in services.

So we can use the decorator center to avoid this adverse situation.
Services can call the decorators as follows:

.. doctest::

    >>> from nicu.decor import deprecated, synchronized

All the decorators should reserve the orginal signature of function decorated,
not only function name/doc/dict, but also function parameters(get by
:func:`inspect.getargspec`).
Using :func:`functools.wraps`, this can only ensure to reserver the function
name/doc/dict, but function parameters have been modified.
So now, we use decorator module to instead of :func:`functools.wraps`, which
can help to reserve function parameters.

.. note::
    :mod:`nicu.decor.decorator` is copied from decorator module.
    The document of decorator module is
    `reference <http://micheles.googlecode.com/hg/decorator/
    documentation.html>`_.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from decorator import decorator, decorator_apply
from info import *
from mode import *
from validator import *
