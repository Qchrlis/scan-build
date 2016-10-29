# -*- coding: utf-8 -*-
#                     The LLVM Compiler Infrastructure
#
# This file is distributed under the University of Illinois Open Source
# License. See LICENSE.TXT for details.
""" This module is a collection of methods commonly used in this project. """

import os
import os.path
import sys
import re
import json
import logging
import functools
import subprocess
from libscanbuild.shell import decode

ENVIRONMENT_KEY = 'INTERCEPT_BUILD'


def duplicate_check(hash_function):
    """ Workaround to detect duplicate dictionary values.

    Python `dict` type has no `hash` method, which is required by the `set`
    type to store elements.

    This solution still not store the `dict` as value in a `set`. Instead
    it calculate a `string` hash and store that. Therefore it can only say
    that hash is already taken or not.

    This method is a factory method, which returns a predicate. """

    def predicate(entry):
        """ The predicate which calculates and stores the hash of the given
        entries. The entry type has to work with the given hash function.

        :param entry: the questioned entry,
        :return: true/false depends the hash value is already seen or not.
        """
        entry_hash = hash_function(entry)
        if entry_hash not in state:
            state.add(entry_hash)
            return False
        return True

    state = set()
    return predicate


def tempdir():
    """ Return the default temporary directory. """

    return os.getenv('TMPDIR', os.getenv('TEMP', os.getenv('TMP', '/tmp')))


def run_build(command, *args, **kwargs):
    """ Run and report build command execution

    :param command: array of tokens
    :return: exit code of the process
    """
    environment = kwargs.get('env', os.environ)
    logging.debug('run build %s, in environment: %s', command, environment)
    exit_code = subprocess.call(command, *args, **kwargs)
    logging.debug('build finished with exit code: %d', exit_code)
    return exit_code


def run_command(command, cwd=None):
    """ Run a given command and report the execution.

    :param command: array of tokens
    :param cwd: the working directory where the command will be executed
    :return: output of the command
    """
    def decode_when_needed(result):
        """ check_output returns bytes or string depend on python version """
        return result.decode('utf-8') if isinstance(result, bytes) else result

    try:
        directory = os.path.abspath(cwd) if cwd else os.getcwd()
        logging.debug('exec command %s in %s', command, directory)
        output = subprocess.check_output(command,
                                         cwd=directory,
                                         stderr=subprocess.STDOUT)
        return decode_when_needed(output).splitlines()
    except subprocess.CalledProcessError as ex:
        ex.output = decode_when_needed(ex.output).splitlines()
        raise ex


def reconfigure_logging(verbose_level):
    """ Reconfigure logging level and format based on the verbose flag.

    :param verbose_level: number of `-v` flags received by the command
    :return: no return value
    """
    # exit when nothing to do
    if verbose_level == 0:
        return

    root = logging.getLogger()
    # tune level
    level = logging.WARNING - min(logging.WARNING, (10 * verbose_level))
    root.setLevel(level)
    # be verbose with messages
    if verbose_level <= 3:
        fmt_string = '%(name)s: %(levelname)s: %(message)s'
    else:
        fmt_string = '%(name)s: %(levelname)s: %(funcName)s: %(message)s'
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=fmt_string))
    root.handlers = [handler]


def command_entry_point(function):
    """ Decorator for command entry methods.

    The decorator initialize/shutdown logging and guard on programming
    errors (catch exceptions).

    The decorated method can have arbitrary parameters, the return value will
    be the exit code of the process. """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        """ Do housekeeping tasks and execute the wrapped method. """

        try:
            logging.basicConfig(format='%(name)s: %(message)s',
                                level=logging.WARNING,
                                stream=sys.stdout)
            logging.getLogger().name = os.path.basename(sys.argv[0])
            return function(*args, **kwargs)
        except KeyboardInterrupt:
            logging.warning('Keyboard interrupt')
            return 130  # signal received exit code for bash
        except Exception:
            logging.exception('Internal error.')
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.error("Please report this bug and attach the output "
                              "to the bug report")
            else:
                logging.error("Please run this command again and turn on "
                              "verbose mode (add '-vvvv' as argument).")
            return 64  # some non used exit code for internal errors
        finally:
            logging.shutdown()

    return wrapper


def wrapper_entry_point(function):
    """ Decorator for wrapper command entry methods.

    The decorator itself execute the real compiler call. Then it calls the
    decorated method. The method will receive dictionary of parameters.

    - compiler:     the compiler name which was executed.
    - command:      the command executed by the wrapper.
    - result:       the exit code of the compilation.

    The return value will be the exit code of the compiler call. (The
    decorated method return value is ignored.)

    If the decorated method throws exception, it will be caught and logged. """

    @functools.wraps(function)
    def wrapper():
        """ It executes the compilation and calls the wrapped method. """

        # get relevant parameters from environment
        parameters = json.loads(os.environ[ENVIRONMENT_KEY])
        # set logging level when needed
        verbose = parameters['verbose']
        reconfigure_logging(verbose)
        # find out what is the real compiler
        wrapper_command = os.path.basename(sys.argv[0])
        is_cxx = re.match(r'(.+)c\+\+(.*)', wrapper_command)
        compiler = parameters['cxx'] if is_cxx else parameters['cc']
        # execute compilation with the real compiler
        command = decode(compiler) + sys.argv[1:]
        logging.debug('compilation: %s', command)
        result = subprocess.call(command)
        logging.debug('compilation exit code: %d', result)
        # call the wrapped method and ignore it's return value ...
        try:
            function(compiler=compiler, command=command, result=result,
                     cc=parameters['cc'], cxx=parameters['cxx'])
        except:
            logging.exception('Compiler wrapper failed complete.')
        # ... return the real compiler exit code instead.
        return result

    return wrapper


def wrapper_environment(args):
    """ Set up environment for interpose compiler wrapper."""

    return {
        ENVIRONMENT_KEY: json.dumps({
            'verbose': args.verbose,
            'cc': args.cc,
            'cxx': args.cxx
        })
    }
