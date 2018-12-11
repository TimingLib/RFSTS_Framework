"""
This Python File is used to render file, filling values with arguments.
This is a simple version to simulate python lib :class:`mako.template.Template`.

Format Support:
    #. ${var} -->
            When value of `var` is tranferred into,
            `${var}` will be replaced by its value.
    #. ${"const_str"} -->
            It will be replaced by `const_str`.
            No difference between quotes and double-quotes.
    #. % if condition:
       true_statement
       % endif
       -->
            If value of `condition` isn't empty,
            replace these sentenses by `true_statement`.
            otherwise, delete these sentenses.
    #. % if condition:
       true_statement
       % else:
       false_statement
       % endif
       -->
            If value of `condition` isn't empty,
            replace these sentenses by `true_statement`.
            otherwise, replace these sentenses by `false_statement`.
"""

from __future__ import with_statement
import sys
import os
import re
import logging


__all__ = [
    "Template",
]

LOGGER = logging.getLogger(__name__)


class Template:
    def __init__(self, content=None, filename=None):
        self.content = ''
        self.tran4str = '-&*&*&*&*&-'
        self.tran5str = '=@!@!@!@!@='
        if content:
            self.content = content
        elif filename:
            with open(filename, 'rb') as fp:
                self.content = fp.read(-1)

    def render(self, **kwargs):
        content = self.content

        # In some situations, for example:
        #   Content: ${'${a}'}
        #   variable a is 10
        # The wanted render result is "${a}", not "10".
        # Any character in ${''} is only a part of string,
        # without special meanings, even though it's a special charater.
        # So as a workaroud, we have to render strings first, and transform
        # special characters to middle strings.
        # And then, render variables and if sentences.
        # At last, we need to revert the middle strings to the orginal
        # characters.
        str_re = re.compile("\$\{\s*['\"](.*?)['\"]\s*\}")
        content = self._replace_all(content, str_re, self._str_value, kwargs)

        var_re = re.compile("\$\{\s*(\w+)\s*\}")
        content = self._replace_all(content, var_re, self._var_value, kwargs)

        if_else_re = re.compile(
            ("%\s*if\s+(\w+)\s*:\s*\n\s*(.*?)"
             "(?:%\s*else\s*:\s*\n\s*(.*?))?"
             "%\s*endif"),
            re.M | re.S)
        content = self._replace_all(
            content, if_else_re, self._if_else_value, kwargs)

        # At last, we should convert the middle string to the last string.
        return content.replace(self.tran4str, '$').replace(self.tran5str, '%')

    def _check_var(self, var, args_dict):
        if var not in args_dict:
            LOGGER.error('Variable "%s" has not been tranferred into render.'
                         % (var))
            raise Exception('render error')
        return

    def _var_value(self, match, args_dict):
        var = match.group(1)
        self._check_var(var, args_dict)
        return args_dict[var]

    def _str_value(self, match, args_dict):
        # Here should change special character '$' and '%' to middle string
        # first. Otherwise, it maybe be regarded as special character.
        const_str = match.group(1)
        return const_str.replace('$', self.tran4str).replace('%', self.tran5str)

    def _if_else_value(self, match, args_dict):
        var = match.group(1)
        body_true = match.group(2)
        body_false = match.group(3)
        self._check_var(var, args_dict)
        return body_true if args_dict[var] else (body_false or '')

    def _replace_all(self, content, match_re, func, args_dict):
        pos = 0
        while True:
            match = match_re.search(content, pos)
            if not match:
                break
            value = func(match, args_dict)
            value = str(value)
            content = content.replace(match.group(0), value)
            pos = match.end() - len(match.group(0)) + len(value)
        return content

