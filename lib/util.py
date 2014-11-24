#!/usr/bin/python

import re


def get_args(my_args=None, args=None, merge=False):
    '''Returns a dict of items in args found in my_args.'''
    args = args if isinstance(args, dict) else {}
    my_args = my_args if isinstance(my_args, dict) else {}
    for arg in args:
        value = args[arg]
        if arg in my_args or merge:
            my_args[arg] = value
    return my_args


def pyv(version):
    '''Returns whether or not the current interpreter is the version specified or newer.'''
    # e.g. >>> sys.version_info
    #      (2, 6, 4, 'final', 0)
    import sys
    i = 0
    for num in version:
        if num > sys.version_info[i]:
            return False
        i += 1
    return True


def pretty_path(path, absolute=False, no_trailing=True):
    if no_trailing:
        path = path.rstrip('/')
    if absolute:
        path = '/' + path
    regex = re.compile(r'/+')
    path = regex.sub('/', path)
    return path


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
