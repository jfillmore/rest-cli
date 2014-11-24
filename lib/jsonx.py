#!/usr/bin/env python

# TODO:
#   * 'grep -v' to selectively hide instead of include
#   * '//foo' floating extraction
#   * filter (or include) results based on values (e.g. "-f 'foo/id >= 3'")
#   * verbose debugging to troubleshoot filtering/extraction

import sys
import re
import collections
try:
    import json
except:
    import simplejson
    json = simplejson


def usage():
    sys.stdout.write('''usage: json [ARGS] [JSON_FILE]

Pretty prints JSON by default. If a file is given it will be read for JSON data; otherwise STDIN will be read instead.

ARGUMENTS:
   -p|--pairs            Convert to name=value for easy variable assignment.
   -h|--help             This information.
   -q|--quiet            If a path cannot be extracted/followed quiety ignore it.
   -j|--json JSON        Parse JSON from command-line parameter instead of from a file.
   -e|--exists PATH      Return a non-zero return status if the specified PATH does not exist. If
                         repeated each PATH must exist. Does not affect output.
   -x|--extract PATH     Extract one or more values from the result matching PATH. May be repeated.
   -X|--exclude PATH     Trim out data from being returned based on a PATH.
   -F|--fs FIELD_SEP     Sets the field separator for path (default: '/').
   -S|--no-sort          Do not sort JSON object keys (default: false).
   -d|--debug            Display debugging information on STDERR.
   -i|--indent INDENT    Indent JSON formatted output with spaces (default: 4).

PATHS
    The JSON data can be filtered based on index, key matches, ranges, etc. The field separator between path parts can be changed with the -F|--fs option.

    Arrays:
        By Index:
         - 'foo/0', 'foo/2', 'foo/-1' (last item)
        By Range:
         - 'foo/:' or 'foo/*' (all items within the array),
         - 'foo/2:', 'foo/:2', 'foo/1:5', 'foo/-2:' (last 2),
         - 'foo/:-2' (all but last two),
         - 'foo/1:-3' (between first and up until 3rd to last)
    Dictionaries:
        Regular Expressions:
         - 'foo/b..?r' = foo/bar, foo/beer
         - 'foo/bar/.*[pP]assw(or)?d' == anything within foo/bar that looks like a password

examples:
    > json='{"id": 3, "name: "bob", "lols": {"a": 1, "b": 2}}'
    > echo "$json" | json -x id -x lols -x lols/b -i 0
    3
    {"a": 1, "b": 2}
    2
    > echo "$json" | json -p -x lols/\*
    lols_a=3
    lols_b=3
''')


def get_opts(defaults, argv):
    i = 1
    opts = defaults
    while i < len(argv):
        arg = argv[i]
        if arg == '-h' or arg == '--help':
            usage()
            exit()
        elif arg == '-q' or arg == '--quiet':
            opts['quiet'] = True
        elif arg == '-p' or arg == '--pairs':
            opts['pairs'] = True
        elif arg == '-e' or arg == '--exists':
            i += 1
            if i == len(argv):
                raise Exception("Missing path to --exists.")
            opts['exists'].append(argv[i])
        elif arg == '-S' or arg == '--no-sort':
            opts['sort_keys'] = False
        elif arg == '-d' or arg == '--debug':
            opts['debug'] = True
        elif arg == '-i' or arg == '--indent':
            i += 1
            if i == len(argv):
                raise Exception("Missing number of spaces to use for --indent.")
            opts['indent'] = int(argv[i])
            if not opts['indent']:
                opts['indent'] = None
        elif arg == '-F' or arg == '--fs':
            i += 1
            if i == len(argv):
                raise Exception("Missing field separator argument to --fs.")
            if len(argv[i]) != 1:
                raise Exception("The field separator must be a single character.")
            opts['separator'] = argv[i]
        elif arg == '-j' or arg == '--json':
            i += 1
            if i == len(argv):
                raise Exception("Missing JSON string for '--json' parameter.")
            if opts['json']:
                raise Exception("JSON data cannot be provided more than once via the '--json' parameter.")
            if opts['json_file']:
                raise Exception("Unable to use both --json and specify a JSON input file.")
            opts['json'] = argv[i]
        elif arg == '-X' or arg == '--exclude':
            i += 1
            if i == len(argv):
                raise Exception("Missing path to --exclude.")
            opts['exclude'].append(argv[i])
        elif arg == '-x' or arg == '--extract':
            i += 1
            if i == len(argv):
                raise Exception("Missing path to --extract.")
            opts['extract'].append(argv[i])
        else:
            # json encoded file
            if opts['json_file']:
                raise Exception("Cannot use '%s'; the JSON input file '%s was already specified." % (arg, opts['json_file']))
            if opts['json']:
                raise Exception("Unable to use both --json and specify a JSON input file.")
            opts['json_file'] = arg
        i += 1
    return opts


def dump_obj(obj, max_len=48):
    txt = json.dumps(obj, ensure_ascii=True)
    if max_len and len(txt) > max_len:
        json_len = len(txt)
        if json_len > max_len:
            third = (max_len / 3)
            third += json_len % 3
            txt = ''.join((
                txt[0:max_len - third],
                '...',
                txt[json_len - third:]
            ))
        return txt


def parse_keys(obj, path, quiet=False):
    """Return the keys that we which to decend into based on the path."""
    keys = []
    try:
        objlen = len(obj)
    except:
        if not quiet:
            raise Exception("Unable to search for path '%s' in non-array object." % (path))
    if isinstance(obj, list):
        # treat * as a full range
        if path == '*':
            path = ':'
        # is it an index value or a range?
        path_split = path.find(':')
        if path_split == -1:
            # index, e.g. -1, 5
            path = int(path)
            # is it in range, or do we not even care?
            if not quiet and (path >= objlen or abs(path) > objlen):
                raise Exception("Invalid index %s in array." % (path))
            else:
                # otherwise return the requested element (rounding if needed on quiet mode)
                if path < 0:
                    keys = [max(path, -1 * objlen)]
                else:
                    keys = [min(path, objlen)]
        else:
            path = path.strip()
            parts = path.split(':')
            if len(parts) != 2:
                raise Exception("Invalid path part: %s." % (path))
            # catch empty; coerce to int
            if parts[0] == '':
                parts[0] = 0
            if parts[1] == '':
                parts[1] = objlen - 1
            parts = [int(part) for part in parts]
            if parts[0] < 0:
                # last X number
                parts[0] = objlen - abs(parts[0])
            if parts[1] < 0:
                # all except last X number
                parts[1] = objlen - abs(parts[1])
            elif parts[1] >= 0:
                # always need one more on positive 2nd numbers
                parts[1] = parts[1] + 1
            keys = range(parts[0], parts[1])
    elif isinstance(obj, dict):
        # write our path into a regex to compare against the keys
        try:
            path_re = re.compile(path)
        except Exception as e:
            raise Exception('Unable to compile path part "%s" to regex: %s' % (path, e))
        keys = [key for key in obj.keys() if re.match(path_re, key)]
    if not len(keys) and not quiet:
        raise Exception("Path '%s' in object '%s' not found." % (
            path,
            dump_obj(obj)
        ))
    return keys


def print_obj(obj):
    json.dumps(
        obj,
        indent=opts['indent'],
        sort_keys=opts['sort_keys'],
        ensure_ascii=True
    )


def exclude_path(obj, path, separator='/', prefix='', quiet=False, debug=False):
    """Exclude values from an object based on a path."""
    # break the path into parts
    path_parts = path.split(separator)
    # keep track of the values we've collected
    excluded = []
    if prefix:
        prefix = prefix + separator
    for key in parse_keys(obj, path_parts[0], quiet):
        # try to get the value
        try:
            value = obj[key]
        except:
            if not quiet:
                raise Exception("Invalid key '%s' not found in object '%s'." % (key, dump_obj(obj)))
            continue
        # our current path thus far
        subpath = prefix + str(key)
        # at the end of our path? we've got what we want here
        if len(path_parts) == 1:
            del obj[key]
        else:
            exclude_path(
                value,
                separator.join(path_parts[1:]),
                separator,
                subpath,
                quiet
            )


def extract_path(obj, path, separator='/', prefix='', quiet=False, debug=False):
    """Extract values from an object based on a path."""
    # break the path into parts
    path_parts = path.split(separator)
    # keep track of the values we've collected
    extracted = []
    if prefix:
        prefix = prefix + separator
    for key in parse_keys(obj, path_parts[0], quiet):
        # try to get the value
        try:
            value = obj[key]
        except:
            if not quiet:
                raise Exception("Invalid key '%s' not found in object '%s'." % (key, dump_obj(obj)))
            continue
        # our current path thus far
        subpath = prefix + str(key)
        # at the end of our path? we've got what we want here
        if len(path_parts) == 1:
            extracted.append((subpath, key, value))
        else:
            extracted += extract_path(
                value,
                separator.join(path_parts[1:]),
                separator,
                subpath,
                quiet
            )
    return extracted


def jsonx(data, indent=4, pairs=False, sort_keys=True, debug=False,
          quiet=False, separator='/', extract=None, exclude=None, exists=None, raw=False):
    if isinstance(data, basestring):
        obj = json.JSONDecoder().decode(data)
    else:
        obj = data
    if exists:
        for path in exists:
            try:
                extract_path(
                    obj,
                    path.strip('/'),
                    separator=separator,
                    quiet=True,
                    debug=debug
                )
            except:
                # QQ, not found
                retval = 1
                break
    # trim out any requested data
    if exclude:
        for path in exclude:
            exclude_path(
                obj,
                path.strip('/'),
                separator=separator,
                quiet=quiet,
                debug=debug
            )
    # we'll print back the obj by default
    results = [obj if raw else json.dumps(
        obj,
        ensure_ascii=True,
        sort_keys=sort_keys,
        indent=indent
    )]
    if extract:
        results = []
        name_re = re.compile(r'\W+')
        for path in extract:
            data = extract_path(
                obj,
                path.strip('/'),
                separator=separator,
                quiet=quiet,
                debug=debug
            )
            for (path, key, value) in data:
                if pairs:
                    results.append("%s=%s" % (
                        re.sub(name_re, '_', path),
                        json.dumps(
                            value,
                            ensure_ascii=True,
                            sort_keys=sort_keys,
                            indent=indent
                        )
                    ))
                else:
                    results.append(value if raw else json.dumps(
                        value,
                        ensure_ascii=True,
                        sort_keys=sort_keys,
                        indent=indent
                    ))
    return results

# stand-alone script mode
if __name__ == '__main__':
    retval = 0
    try:
        opts = get_opts({
            'indent': 4,
            'pairs': False,
            'sort_keys': True,
            'json': False,
            'debug': False,
            'quiet': False,
            'separator': '/',
            'json_file': None,
            'extract': [],
            'exclude': [],
            'exists': []
        }, sys.argv)

        # we got something, right?
        if opts['json']:
            json_data = opts['json']
        elif opts['json_file']:
            json_file = open(opts['json_file'])
            json_data = ''.join(json_file.readlines())
        else:
            # try reading stdin for data
            json_data = ''.join(sys.stdin.readlines())
        if not json_data:
            raise Exception("No JSON given to parse.")
        # we'll pass the JSON explicitly
        del opts['json']
        del opts['json_file']
        results = jsonx(json_data, **opts)
        for result in results:
            print result
    except Exception, e:
        sys.stderr.write(e.message + "\n")
        retval = 1
    sys.exit(retval)
