import sys
import time
import logging
import types
import threading
import functools

from nicu.kthread import KThread


__all__ = [
    "synchronized",
    "asynchronized",
    "TimeoutError",
    "timeout",
    "retries",
    "cached_property",
    "addto",
]

LOGGER = logging.getLogger(__name__)


def synchronized(lock):
    """
    Synchronization Decorator.

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference Decorator: synchronized
    """
    def _synchronized(func):
        @functools.wraps(func)
        def _f(*func_args, **func_kwargs):
            lock.acquire()
            try:
                return func(*func_args, **func_kwargs)
            finally:
                lock.release()
        return _f
    return _synchronized


def asynchronized(stoppable=False):
    """
    Make a function immediately return a function of no args which,
    when called, waits for the result, which will start being processed
    in another thread.

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference Decorator: lazy_thunkify
    """
    def _asynchronized(func):
        @functools.wraps(func)
        def _f(*func_args, **func_kwargs):
            def _exec():
                try:
                    func_result = func(*func_args, **func_kwargs)
                    result[0] = func_result
                except Exception, e:
                    exc[0] = True
                    exc[1] = sys.exc_info()
                    print('"%s" thrown an exception: %s\n.%s' %
                          (_f.func_name, str(e), str(exc)))
                finally:
                    wait_event.set()

            def wait():
                wait_event.wait()
                if exc[0]:
                    raise exc[1][0], exc[1][1], exc[1][2]
                return result[0]

            def is_alive():
                return not wait_event.isSet()

            def stop():
                async_thread.kill()
                return

            wait_event = threading.Event()
            result = [None]
            exc = [False, None]
            async_thread = None
            if stoppable:
                async_thread = KThread(target=_exec)
            else:
                async_thread = threading.Thread(target=_exec)
            async_thread.start()
            wait.is_alive = is_alive
            if stoppable:
                wait.stop = stop

            return wait
        return _f
    return _asynchronized


class TimeoutError(Exception):
    pass


def timeout(seconds):
    """
    This Decorator is used to limit the time.
    Exception will be thrown when function isn't return in time.

    Reference: http://www.cnblogs.com/fengmk2/archive/2008/08/30/
            python_tips_timeout_decorator.html
    Reference Decorator: timeout
    """
    def _timeout(func):
        def _new_func(oldfunc, result, oldfunc_args, oldfunc_kwargs):
            result.append(oldfunc(*oldfunc_args, **oldfunc_kwargs))

        @functools.wraps(func)
        def _f(*func_args, **func_kwargs):
            result = []
            # create new args for _new_func,
            # because we want to get the func return value to result list
            new_kwargs = {
                'oldfunc': func,
                'result': result,
                'oldfunc_args': func_args,
                'oldfunc_kwargs': func_kwargs
            }
            kt = KThread(target=_new_func, args=(), kwargs=new_kwargs)
            kt.start()
            kt.join(seconds)
            alive = kt.isAlive()
            kt.kill()  # kill the child thread
            if alive:
                raise TimeoutError('"%s" run too long, timeout %d seconds.' %
                                   (_f.func_name, seconds))
            else:
                return result[0]
        return _f
    return _timeout


# Copyright 2012 by Jeff Laughlin Consulting LLC
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
def retries(max_tries, delay=1, backoff=2, exceptions=(Exception,), hook=None):
    """
    Function Decorator implementing retrying logic.

    delay: Sleep this many seconds * backoff * try number after failure
    backoff: Multiply delay by this factor after each failure
    exceptions: A tuple of exception classes; default (Exception,)
    hook: A function with the signature myhook(tries_remaining, exception,
            delay), default None
        tries_remaining: The number of tries remaining.
        exception: The exception instance which was raised.
        delay: The time to sleep

    The Decorator will call the function up to max_tries times if it raises
    an exception.

    By default it catches instances of the Exception class and subclasses.
    This will recover after all but the most fatal errors. You may specify a
    custom tuple of exception classes with the 'exceptions' argument; the
    function will only be retried if it raises one of the specified
    exceptions.

    Additionally you may specify a hook function which will be called prior
    to retrying with the number of remaining tries and the exception instance;
    see given example. This is primarily intended to give the opportunity to
    log the failure. Hook is not called after failure if no retries remain.

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference Decorator: retries
    """
    def _retries(func):
        @functools.wraps(func)
        def _f(*func_args, **func_kwargs):
            mydelay = delay
            tries = range(max_tries)
            tries.reverse()
            for tries_remaining in tries:
                try:
                    return func(*func_args, **func_kwargs)
                except exceptions, e:
                    if tries_remaining > 0:
                        if hook is not None:
                            hook(tries_remaining, e, mydelay)
                        time.sleep(mydelay)
                        mydelay = mydelay * backoff
                    else:
                        raise
                else:
                    break
        return _f
    return _retries


# @2011 Christopher Arndt, MIT License
class cached_property(object):
    """
    Decorator for read-only properties evaluated only once within TTL period.

    The value is cached  in the '_cache' attribute of the object instance that
    has the property getter method wrapped by this Decorator. The '_cache'
    attribute value is a dictionary which has a key for every property of the
    object which is wrapped by this Decorator. Each entry in the cache is
    created only when the property is accessed for the first time and is a
    two-element tuple with the last computed property value and the last time
    it was updated in seconds since the epoch.

    The default time-to-live (TTL) is 300 seconds (5 minutes). Set the TTL to
    zero for the cached value to never expire.

    To expire a cached property value manually just do:
        del instance._cache[<property name>]

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference Decorator: cached_property
    """
    def __init__(self, ttl=300):
        self.ttl = ttl

    def __call__(self, fget, doc=None):
        self.fget = fget
        self.__doc__ = doc or fget.__doc__
        self.__name__ = fget.__name__
        self.__module__ = fget.__module__
        return self

    def __get__(self, inst, owner):
        now = time.time()
        try:
            value, last_update = inst._cache[self.__name__]
            if self.ttl > 0 and now - last_update > self.ttl:
                raise AttributeError
        except (KeyError, AttributeError):
            value = self.fget(inst)
            try:
                cache = inst._cache
            except AttributeError:
                cache = inst._cache = {}
            cache[self.__name__] = (value, now)
        return value


def addto(instance):
    """
    Decorator for adding method to a class instance.

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference Decorator: addto
    """
    def _addto(func):
        func = types.MethodType(func, instance, instance.__class__)
        setattr(instance, func.func_name, func)
        return func
    return _addto

