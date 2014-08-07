# -*- coding: utf-8 -*-
#                     The LLVM Compiler Infrastructure
#
# This file is distributed under the University of Illinois Open Source
# License. See LICENSE.TXT for details.

import logging
import functools


def trace(function):
    """ Decorator to simplify debugging. """
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        logging.debug('entering {0}'.format(function.__name__))
        result = function(*args, **kwargs)
        logging.debug('leaving {0}'.format(function.__name__))
        return result

    return wrapper


def require(required=[]):
    """ Decorator for checking the required values in state.

    It checks the required attributes in the passed state and stop when
    any of those is missing.
    """
    def decorator(function):
        @functools.wraps(function)
        def wrapper(opts, cont):
            try:
                precondition(opts)
                return function(opts, cont)
            except Exception as e:
                logging.error(str(e))
                return None

        def precondition(opts):
            for key in required:
                if key not in opts:
                    raise KeyError(
                        '{0} not passed to {1}'.format(key, function.__name__))

        return wrapper

    return decorator
