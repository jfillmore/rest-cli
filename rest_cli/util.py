import re


def get_args(my_args=None, args=None, merge=False):
    """
    Returns a dict of items in args found in my_args.
    """
    args = args if isinstance(args, dict) else {}
    my_args = my_args if isinstance(my_args, dict) else {}
    for arg in args:
        value = args[arg]
        if arg in my_args or merge:
            my_args[arg] = value
    return my_args


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
