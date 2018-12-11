'''
This module only has decorator :func:`valid_param`.
'''
import inspect
import re
import logging

import decor


__all__ = [
    "valid_param",
    "ValidateError",
    "null_ok",
    "multi_type",
]

LOGGER = logging.getLogger(__name__)


class ValidateError(Exception):
    pass


def valid_param(*varargs, **keywords):
    """
    Decorator is used to validate legality of parameters.

    A example to use this decorator as follows:

    .. doctest::

        >>> from validator import valid_param, null_ok, multi_type
        >>> @valid_param(i=int)
        >>> def foo(i):
        ...     return i+1

    **Reference:** `<http://www.cnblogs.com/huxi/archive/2011/03/31/
    2001522.html>`_

    **Reference Decorator:** `validParam`
    """
    varargs = map(_to_stardard_condition, varargs)
    keywords = dict((k, _to_stardard_condition(keywords[k]))
                    for k in keywords)

    def _valid_param(func, *func_args, **func_kwargs):
        args, varargname, kwname = inspect.getargspec(func)[:3]
        dct_validator = _getcallargs(args, varargname, kwname,
                                     varargs, keywords)
        dct_call_args = _getcallargs(args, varargname, kwname,
                                     func_args, func_kwargs)
        k, item = None, None
        try:
            for k in dct_validator:
                if k == varargname:
                    for item in dct_call_args[k]:
                        assert dct_validator[k](item)
                elif k == kwname:
                    for item in dct_call_args[k].values():
                        assert dct_validator[k](item)
                else:
                    item = dct_call_args[k]
                    assert dct_validator[k](item)
        except:
            raise ValidateError('%s() parameter validation fails, '
                                'param: %s, value: %s(%s)'
                                % (func.func_name, k, item,
                                   item.__class__.__name__))
        return func(*func_args, **func_kwargs)
    return decor.decorator(_valid_param)


def _to_stardard_condition(condition):
    """
    Change condition to check function.
    """
    if inspect.isclass(condition):
        return lambda x: isinstance(x, condition)

    if isinstance(condition, (tuple, list)):
        cls, condition = condition[:2]
        if condition is None:
            return _to_stardard_condition(cls)

        if cls in (str, unicode) and condition[0] == condition[-1] == '/':
            return lambda x: (isinstance(x, cls)
                              and re.match(condition[1:-1], x) is not None)

        return lambda x: isinstance(x, cls) and eval(condition)

    return condition


def null_ok(cls, condition=None):
    """
    Make value "None" is accepted by this condition.
    """
    return lambda x: x is None or _to_stardard_condition((cls, condition))(x)


def multi_type(*conditions):
    """
    Check whether value meets one of these conditions.
    """
    lst_validator = map(_to_stardard_condition, conditions)

    def validate(x):
        for v in lst_validator:
            if v(x):
                return True
    return validate


def _getcallargs(args, varargname, kwname, varargs, keywords):
    """
    Get a dict, whose key is parameter name, and value is parameter value.
    """
    dct_args = {}
    varargs = tuple(varargs)
    keywords = dict(keywords)

    argcount = len(args)
    varcount = len(varargs)
    callvarargs = None

    if argcount <= varcount:
        for n, argname in enumerate(args):
            dct_args[argname] = varargs[n]

        callvarargs = varargs[-(varcount - argcount):]

    else:
        for n, var in enumerate(varargs):
            dct_args[args[n]] = var

        for argname in args[-(argcount - varcount):]:
            if argname in keywords:
                dct_args[argname] = keywords.pop(argname)

        callvarargs = ()

    if varargname is not None:
        dct_args[varargname] = callvarargs

    if kwname is not None:
        dct_args[kwname] = keywords

    dct_args.update(keywords)
    return dct_args



