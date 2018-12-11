"""
This module is the center of all decorators.

Usually, services call the decorators as follows:
    from nicu._decorator.info import deprecated
    from nicu._decorator.mode import synchronized

As more and more decorators added into CommonUtil later, the classification
of decorators may change. So each decorator may be divided into another file,
which leds to modify the code related in services.

So we can use the decorator center to avoid this adverse situation.
Services can call the decorators as follows:
    from nicu.decorator import deprecated, synchronized
"""

from _decorator.info import *
from _decorator.mode import *
from _decorator.validator import *
