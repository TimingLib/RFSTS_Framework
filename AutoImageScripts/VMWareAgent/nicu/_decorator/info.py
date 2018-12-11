import sys
import logging
import functools
import os
import linecache


__all__ = [
    "deprecated",
    "dump_args",
    "trace",
]

LOGGER = logging.getLogger(__name__)


def deprecated(func):
    """
    This is a decorator which can be used to mark functions as deprecated.
    It will result in a warning being emitted when the function is used.

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference decorator: deprecated
    """
    @functools.wraps(func)
    def _f(*func_args, **func_kwargs):
        LOGGER.warning('DeprecationWarning: Call to deprecated function'
                       ' "%s".' % (func.__name__))
        return func(*func_args, **func_kwargs)
    return _f


def dump_args(func):
    """
    This decorator dumps out all the arguments passed to a function before
    calling it.

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference: http://stackoverflow.com/questions/6200270/decorator-to-print-
        function-call-details-parameters-names-and-effective-values
    Reference decorator: dumpArgs
    """
    @functools.wraps(func)
    def _f(*func_args, **func_kwargs):
        arg_names = func.func_code.co_varnames[:func.func_code.co_argcount]
        args = func_args[:len(arg_names)]
        defaults = func.func_defaults or ()
        args = args + defaults[len(defaults) -
                               (func.func_code.co_argcount - len(args)):]
        params = zip(arg_names, args)
        args = func_args[len(arg_names):]
        if args:
            params.append(('args', args))
        if func_kwargs:
            params.append(('kwargs', func_kwargs))
        LOGGER.info(func.func_name + '(' +
                    ', '.join('%s=%r' % p for p in params) + ')')
        return func(*func_args, **func_kwargs)
    return _f


class trace(object):
    """
    This decorator is used to trace each line of individual functions.

    Reference: https://wiki.python.org/moin/PythonDecoratorLibrary
    Reference decorator: trace
    """
    def __init__(self, level=-1):
        self.level = level
        self.cur_level = -1

    def __call__(self, func):
        def print_trace(frame, why, arg):
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno
            bname = os.path.basename(filename)
            LOGGER.info("%s(%d): %s" % (bname, lineno,
                                        linecache.getline(filename, lineno)))
            return

        def global_trace(frame, why, arg):
            if why == "call":
                self.cur_level += 1
                if self.level < 0 or self.cur_level <= self.level:
                    print_trace(frame, why, arg)
                return local_trace
            return None

        def local_trace(frame, why, arg):
            if why == "line":
                # record the file name and line number of every trace
                if self.level < 0 or self.cur_level <= self.level:
                    print_trace(frame, why, arg)
            elif why == "return":
                self.cur_level -= 1
            return local_trace

        @functools.wraps(func)
        def _f(*func_args, **func_kwargs):
            sys.settrace(global_trace)
            try:
                result = func(*func_args, **func_kwargs)
            finally:
                sys.settrace(None)
            return result

        return _f



