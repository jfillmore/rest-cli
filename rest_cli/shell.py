#!/usr/bin/python -tt

"""
Shell for interacting with a RESTful server.
"""


from collections import namedtuple
from traceback import print_exception
import json
import os
import os.path
import re
import shlex  # simple lexical anaysis for command line parsing
import socket
import subprocess  # for shell commands
import sys

# import hacks!
os.environ['TERM'] = 'linux'
import readline

from .jsonx import jsonx
from .htmlx import htmlx
from . import client
from . import dbg
from . import util


xml_content_types = [
    'application/xhtml+xml',
    'application/xml',
    'text/html',
    'text/xml'
]

DataMap = namedtuple('DataMap', ['key', 'path'])


class JSONException(Exception):
    pass


class Shell:
    """
    Shell for interacting with REST client.
    """
    # a list of our internal commands
    http_methods = (
        'get',
        'post',
        'put',
        'patch',
        'delete',
        'options'
    )
    method_aliases = {
        'del': 'delete',
        'opts': 'options',
        'opt': 'options',
        '?': 'options'
    }
    cmds = {
        'set': {},
        'cd': {},
        'reload': {},
        'config': {},
        'help': {},
        'quit': {},
        'sh': {}
    }
    _env = {
        'cwd': '/',  # where in the URL we are operating
        'last_cwd': '/',
        'histfile': None,
        'vars': {}  # automatically added to each API call
    }
    decode = json.JSONDecoder().decode
    encode = json.JSONEncoder().encode

    def __init__(self, argv):
        self.last_rv = False
        self.env(
            'histfile',
            os.path.join(os.path.expanduser('~'), '.rest-cli_history')
        )
        self.main_args = {
            'color': sys.stdout.isatty(),
            'formatted': True,
            'headers': {},
            'help': False,
            'insecure': False,
            'shell': False,
            'url': 'https://localhost:443/',
            'verbose': False,
        }
        self.data_store = {}
        # parse out our initial args
        self.args = self.parse_args(argv, self.main_args)
        self.client = client.RESTClient(self.args['url'], self.args['insecure'])
        if self.args['help']:
            return
        # run our initial command, possibly invoking shell mode after
        self.parse_cmd(argv)
        if self.args['shell']:
            self.start()

    def start(self, read_history=True):
        # load our history
        if read_history:
            try:
                readline.read_history_file(self.env('histfile'))
            except:
                pass
        # run APIs until the cows come home
        try:
            repeat = False
            while self.parse_cmd(raw_input(self.get_prompt())):
                pass
        except KeyboardInterrupt as e:
            pass
        except EOFError as e:
            pass
        except ValueError as e:
            dbg.log('Input error: ' + str(e) + '\n', symbol='!')
            repeat = True
        except Exception as e:
            dbg.log(str(e) + '\n', symbol='!')
            repeat = True
        if repeat:
            self.start(False)
        else:
            dbg.log('\n')
            self.stop()
            return self.last_rv

    def stop(self):
        # save our history
        readline.write_history_file(self.env('histfile'))

    def get_prompt(self):
        # : using colors messes up term spacing w/ readline history support
        # http://bugs.python.org/issue12972
        # likely fixed in 3.2+? -- 2.7.5 seems buggy still
        if self.args['color'] and sys.version_info >= (3, 2):
            prompt = ''.join([
                '\033[0;31m',
                '[',
                '\033[1;31m',
                self.env('cwd'),
                '\033[0;31m',
                '] ',
                '\033[0;37m',
                '> ',
                '\033[0;0m'
            ])
        else:
            prompt = ' '.join([
                self.env('cwd'),
                '> '
            ])
        return prompt

    def set_edit_mode(self, mode):
        # TODO: figure out why 'vi' doesn't let you use the 'm' key :/
        modes = ['vi', 'emacs']
        if mode in modes:
            readline.parse_and_bind(''.join(['set', 'editing-mode', mode]))
            self.args['edit_mode'] = mode
        else:
            raise Exception(''.join(['Invalid editing mode: ', mode, ' Supported modes are: ', ', '.join(modes), '.']))

    def print_help(self, shell=False):
        dbg.log("""usage: rest-cli http-verb|command API [API_PARAMS] [ARGUMENTS]

ARGUMENTS
---------------------------------------------------------------------------

HTTP OPTIONS (each may be specified multiple times)
   -f, --form               Override default of sending JSON data
   -H, --header HEADER      HTTP header (e.g. 'Foo: bar') .
   -Q, --query QUERY_DATA   Query data to include (e.g. foo=bar&food=yummy).
   -d, --data NAME[+]=PATH  Store response data; '+' also adds variable to the env


OTHER OPTIONS (may also be set via 'set' command)
   -B, --basic USER:PASS    HTTP basic authentication.
   -c, --color              Color formatted JSON responses (default=True).
   -C, --no-color           Do not color formatted JSON responses.
   -h, --help               This information.
   -I, --invert             Invert colors in formatted JSON responses.
       --insecure           Do not valid SSL certificates (danger!)
   -j, --json STRING        Append JSON-encoded list to API parameters.
   -q, --quiet              Do not print API return response.
   -r, --raw                Don't format response data; return raw response.
   -s, --shell              Shell mode for running multiple APIs within a session.
   -u, --url URL            URL to the API location (default: https://localhost/).
   -v, --verbose            Print verbose debugging info to stderr.
   -x, --extract PATH       Parse JSON/(X)HTML to only return requested data; may be repeated.
   -X, --exclude PATH       Exclude specified path from JSON data; may be repeated.

API PARAMS
---------------------------------------------------------------------------
Dictionaries can be created on demand using dot notation. Multiple params within the same dictionary will merge together. Values are always encoded as strings unless ":=" is used to assign the value.

   foo                      {"foo": true}
   ^foo                     {"foo": false}
   foo=bar                  {"foo": "bar"}
   foo.bar=3 foo.bard=abc   {"foo": {"bar": "3", "bard": "abc"}}
   foo:='{"bar":3}'         {"foo": {"bar": 3}}
   foo.bar:=3.14            {"foo": {"bar": 3.14}}

Variables in memory (e.g. shown by 'data' command) may be referenced using "+=" as the operator.


HTML/XML PATHS (--extract, --data)
---------------------------------------------------------------------------
Values are extracted using 'pgquery', a Python port of jQuery. This can be used to extract and store values from input forms.


JSON PATHS  (--extract, --exclude, --data)
---------------------------------------------------------------------------
The JSON data can be filtered based on index, key matches, ranges, etc.

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

SHELL COMMANDS
---------------------------------------------------------------------------
   cd                       Change the base URL (e.g. "cd customers/8; cd ../9").
   help                     This information.
   quit                     Adios! (quit shell).
   set                      Set configuration options.
   config                   List current configuration infomation.
   sh CMD                   Run a BASH shell command.
   data [NAME] [-=NAME]     List variables in memory, optionally by name; -= to remove from memory
   env [NAME] [[+-]=NAME]   List environmental variables, optionally by name; += or -= to add/remove 'data' from the environment
   > FILE                   Write API response to specified file.
   >> FILE                  Append API response to specified file.

EXAMPLES:
---------------------------------------------------------------------------
    rest-cli -u https://foo.com/api -s
    > get site/foo.com -v
    > post site -j domain=foo.com
    > cd site/foo.com
    > get ./

""")

    def parse_args(self, expr, arg_slice=None):
        args = {
            'FILES': [],
            'api_args': {},
            'basic_auth': None,
            'cmd_args': [],
            'color': self.main_args['color'],
            'data': [],
            'exclude': [],
            'extract': [],
            'formatted': self.main_args['formatted'],
            'headers': {},
            'help': False,  # user just wanted some help
            'insecure': False,
            'invert_color': False,
            'path': None,
            'query': [],
            'redir_type': None,
            'shell': False,
            'stdout_redir': None,
            'url': self.main_args['url'],
            'verb': None,
            'verbose': False,
        }
        if isinstance(expr, str):
            parts = shlex.split(expr)
        else:
            parts = expr  # already a list
        # check for any condensed parameters (e.g. -fr = -f, -r)
        old_parts = parts[:]
        for i in range(0, len(parts)):
            part = parts[i]
            if len(part) > 2 and part[0] == '-' and not (part[1] in ['-', '+', '=']):
                # expand the parameters out
                parts = parts[:i] + \
                    [''.join(['-', param]) for param in parts[i][1:]] + \
                    parts[i + 1:]
        i = 0
        # iterate through each paramter and handle it
        while i < len(parts):
            part = parts[i]
            if len(part) == 0:
                pass
            elif part == '>' or part[0] == '>' or part == '>>':
                # output redirection! woot
                if part == '>' or parts == '>>':
                    i += 1
                    if part == '>':
                        args['redir_type'] = 'w'
                    else:
                        args['redir_type'] = 'a'
                    if i == len(parts):
                        raise Exception("Missing file path to output result to.")
                    args['stdout_redir'] = parts[i]
                else:
                    if len(part) > 1 and part[0:2] == '>>':
                        args['stdout_redir'] = part[2:]
                        args['redir_type'] = 'a'
                    else:
                        args['stdout_redir'] = part[1:]
                        args['redir_type'] = 'w'
            elif part == '-B' or part == '--basic':
                i += 1
                if i == len(parts):
                    raise Exception("Missing HTTP basic auth user/pass parameter.")
                if ':' not in parts[i]:
                    raise Exception("Expected HTTP basic auth in format 'user:pass'.")
                args['basic_auth'] = parts[i]
            elif part == '-F' or part == '--file':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for file to upload.")
                # collect up the name
                if parts[i].find('=') == -1 or parts[i].find('&') != -1:
                    raise Exception("Invalid file name=file_path pair.")
                (name, path) = parts[i].split('=', 1)
                # make sure the file exists
                if not os.path.isfile(path):
                    raise Exception("Unable to either read or locate file '%s." % path)
                args['FILES'][name] = path
                raise Exception("Not supported at the moment")
            elif part == '-Q' or part == '--query':
                i += 1
                if i == len(parts):
                    raise Exception("Missing query name=value pair.")
                # make sure we have a valid pair
                if parts[i].find('=') == -1 or parts[i].find('&') != -1:
                    raise Exception("Invalid query name=value pair.")
                args['query'].append(parts[i])
            elif part == '-i' or part == '--invert':
                args['invert_color'] = True
            elif part == '--insecure':
                args['insecure'] = True
            elif part == '-c' or part == '--color':
                args['color'] = True
            elif part == '-C' or part == '--no-color':
                args['color'] = False
            elif part == '-v' or part == '--verbose':
                args['verbose'] = True
            elif part == '-f' or part == '--form':
                args['headers']['content-type'] = 'application/x-www-form-urlencoded'
            elif part == '-h' or part == '--help':
                self.print_help()
                args['help'] = True
            elif part == '-H' or part == '--header':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for HTTP header.")
                h_parts = parts[i].split(': ', 1)
                if len(h_parts) != 2:
                    raise Exception("Invalid HTTP header.")
                args['headers'][h_parts[0].lower()] = h_parts[1]
            elif part == '-s' or part == '--shell':
                args['shell'] = True
            elif part == '-j' or part == '--json':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for JSON API params.")
                try:
                    api_args = self.decode(parts[i])
                    if isinstance(api_args, dict):
                        args['api_args'].update(api_args)
                    else:
                        raise JSONException("JSON values must be a dictionary of arguments.")
                except JSONException as e:
                    dbg.log('Invalid JSON:' + e.message)
                    raise e
                except Exception as e:
                    dbg.log('Invalid JSON:' + e.message)
                    raise JSONException(e.message)
            elif part == '-r' or part == '--raw':
                args['formatted'] = False
            elif part == '--url' or part == '-u':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for URL.")
                args['url'] = parts[i]
            elif part == '-d' or part == '--data':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for --data.")
                part = parts[i]
                if part.index('=') == -1:
                    raise Exception("Invalid parameter for --data: expected format NAME[+]=PATH")
                args['data'].append(DataMap(*part.split('=', 1)))
            elif part == '-x' or part == '--extract':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for --extract.")
                args['extract'].append(parts[i])
            elif part == '-X' or part == '--exclude':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for --exclude.")
                args['exclude'].append(parts[i])
            else:
                # we always pick up the command/method first
                if args['verb'] is None:
                    args['verb'] = part.lower()
                    # process any aliases
                    if args['verb'] in self.method_aliases:
                        args['verb'] = self.method_aliases[args['verb']]
                elif args['verb'] in self.http_methods and args['path'] is None:
                    # collect the API -- unless this is a internal command
                    args['path'] = util.pretty_path(self.parse_path(part), False, False)
                else:
                    # anything else is a parameter
                    if args['verb'] in self.http_methods:
                        # get the name/value
                        args['api_args'] = self.parse_param(part, args['api_args'])
                    else:
                        args['cmd_args'].append(part)
            i += 1
        if arg_slice is not None:
            args = util.get_args(arg_slice, args)
        return args

    def parse_cmd(self, cli_cmd):
        """
        Parse a shell command to either run an internal command or perform an
        HTTP request. Returns True if a command was successfully parsed, false
        if the user wants to quit, or throws an exception with a syntax or
        run-time/request error.

        Commands/requests are executed using the current environment and/or
        base arguments.

        By default, responses are printed to standard-out based on the run-time
        parameters. Output can be piped to write/append files like a normal
        shell (e.g. if using inside the rest shell).
        """
        # collect up the command parts
        args = self.parse_args(cli_cmd)
        # not writing to a file by default
        file = None
        # run the command or API
        answer = None
        if args['verb'] is None or len(args['verb']) == 0:
            if self.args['shell']:
                # no command, just do nothing
                return True
            else:
                # no command and not in shell mode? offer some help
                self.print_help()
                self.last_rv = 1
                return True
        elif args['verb'] in self.http_methods:
            # run an API
            try:
                args['api_args'].update(self.env('vars'))
                answer = self.client.request(
                    method=args['verb'],
                    path=args['path'],
                    params=args['api_args'],
                    query=args['query'],
                    headers=args['headers'],
                    verbose=args['verbose'],
                    basic_auth=args['basic_auth'],
                    full=True
                )
                response = answer.decoded
                response_status = None
                success = True
            except client.ApiException as e:
                success = False
                response_status = str(e)
                response = e.response.decoded
                answer = e.response
            except socket.error as e:
                response_status = str(e)
                response = None
                success = False
                answer = None
            self.last_rv = int(not success)
            # prep response redirection, since it worked
            if args['stdout_redir'] is not None:
                try:
                    file = open(args['stdout_redir'], args['redir_type'])
                except IOError as e:
                    dbg.log('Failed to write response: ' + e + '\n', symbol='!')
                    return True
        else:
            # run an internal command
            try:
                return self.run_cmd(args['verb'], args['cmd_args'])
            except Exception as e:
                response_status = 'Syntax Error'
                response = e.message
                success = False
                if args['verbose']:
                    print_exception(*sys.exc_info())
        # adjust the response object as requested
        if answer and (args['extract'] or args['exclude'] or args['data']):
            # handle HTML vs JSON differently
            content_type = answer.obj.headers.get('Content-Type')
            to_store = {}
            if content_type.startswith("application/json"):
                try:
                    response = jsonx(
                        response,
                        extract=args['extract'],
                        exclude=args['exclude'],
                        raw=True,
                        data_map=args['data'],
                        data_store=to_store
                    )
                    # if we only had one match return it instead of a single-element array for cleanliness
                    if len(response) == 1:
                        response = response[0]
                except:
                    (exc_type, exc_msg, exc_tb) = sys.exc_info()
                    dbg.log('%s\n' % exc_msg, symbol='!')
                    return True
            elif any([content_type.startswith(xml_type) for
                      xml_type in xml_content_types]):
                # it looks like HTML so try parsing that out instead
                try:
                    response = htmlx(
                        response,
                        extract=args['extract'],
                        data_map=args['data'],
                        data_store=to_store
                    )
                    # if we only had one match return it instead of a single-element array for cleanliness
                    if len(response) == 1:
                        response = response[0]
                except:
                    (exc_type, exc_msg, exc_tb) = sys.exc_info()
                    dbg.log('%s\n' % exc_msg, symbol='!')
                    return True
            # if we ended up storing any data, save it memory, noting any environmentals
            for key in to_store:
                # coerce single-values out of lists to stand on their own
                if len(to_store[key]) == 1:
                    to_store[key] = to_store[key][0]
                clean_key = key
                if key.endswith('+'):
                    clean_key = key[:-1]
                self.data_store[clean_key] = to_store[key]
                if key.endswith('+'):
                    self.env('vars')[clean_key] = to_store[key]
        self._print_response(
            success,
            response,
            response_status,
            formatted=args['formatted'],
            color=args['color'],
            invert_color=args['invert_color'],
            stdout_redir=args['stdout_redir'],
            redir_type=args['redir_type'],
            file=file
        )
        return True

    def _print_response(self, success, response, status=None, **args):
        if success:
            if response is not None:
                if 'stdout_redir' in args and args['stdout_redir'] is not None:
                    #response = json.dumps(
                    #    response,
                    #    ensure_ascii=True,
                    #    sort_keys=True,
                    #    indent=4
                    #)
                    args['file'].write(dbg.obj2str(response, color=False))
                    args['file'].close()
                else:
                    if isinstance(response, str):
                        if args.get('formatted'):
                            chars_to_print = min(len(response), 256)
                            dbg.log('# %d/%d chars%s\n' % (
                                chars_to_print,
                                len(response),
                                (
                                    ", use --raw|-r to see full output"
                                    if chars_to_print < len(response)
                                    else ""
                                )
                            ))
                            print(response[0:chars_to_print])
                        else:
                            print(response)
                    else:
                        if args.get('formatted'):
                            dbg.pretty_print(
                                response,
                                color=args.get('color'),
                                invert_color=args.get('invert_color')
                            )
                        else:
                            print(json.dumps(response, indent=4, sort_keys=True))
        else:
            if isinstance(response, str):
                if args['formatted']:
                    chars_to_print = min(len(response), 256)
                    dbg.log('%s (%d/%d chars)\n:%s' % (
                        status,
                        chars_to_print,
                        len(response),
                        response[0:chars_to_print]
                    ), symbol='!')
                else:
                    dbg.log('%s:\n%s' % (
                        status, response
                    ), symbol='!')
            else:
                dbg.log('%s:' % (status), symbol='!', color='31')
                if response is not None:
                    if args.get('formatted'):
                        dbg.pretty_print(
                            response,
                            color=args.get('color'),
                            invert_color=args.get('invert_color')
                        )
                    else:
                        print(json.dumps(response, indent=4, sort_keys=True))

    def env(self, key, value=None):
        """
        Fetch or set a value from the environment.
        """
        key = key.lower()
        if key in self._env:
            if value is None:
                return self._env[key]
            else:
                # remember the last dir when changing it
                if key == 'cwd':
                    self._env['last_cwd'] = self._env['cwd']
                self._env[key] = value
                return value

    def parse_param(self, str, params={}):
        """
        Parse a CLI parameter, optionally merging it with existing passed
        parameters.

        Parameter encoding:

        'foo', '!foo' 
            Bare word are treated as boolean values. True by default, false if
            starting with an exclaimation point.

        'foo=bar', 'foo=0', 'foo.bar=42'
            Assign the string value to the key specified. If the key contains
            dots than objects will be created automatically.

        'foo:=3', 'foo.bar:=["a", "b", "c"]'
            Assign the JSON-encoded values to the key specified.
        """
        param_parts = str.split('=', 1)
        param = param_parts[0]
        # no value given? treat it as a boolean
        if len(param_parts) == 1:
            if param.startswith('^'):
                value = False
            else:
                value = True
            param = param.lstrip('^')
        else:
            value = param_parts.pop()
            # check to see if we have a JSON value or are fetching from memory
            if param.endswith(':'):  # e.g. 'foo:={"bar":42}'
                value = self.decode(value)
                param = param.rstrip(':')
            elif param.endswith('+'):
                param = param.rstrip('+')
                if param not in self.data_store:
                    raise Exception('Variable "%s" is not in memory' % param)
                value = self.data_store[param]
        # check the name to see if we have a psuedo array
        # (e.g. 'foo.bar=3' => 'foo = {"bar": 3}')
        if param.find('.') == -1:
            params[param] = value
        else:
            # break the array into the parts
            p_parts = param.split('.')
            key = p_parts.pop()
            param_ptr = params
            for p_part in p_parts:
                if not p_part in param_ptr:
                    param_ptr[p_part] = {}
                param_ptr = param_ptr[p_part]
            param_ptr[key] = value
        return params

    def parse_path(self, path=''):
        """
        Returns a path that may contain relative references (e.g.  "../foo")
        based on our current path.
        """
        # no path? go to our last working dir
        if not len(path) or path == '-':
            return self._env['last_cwd']
        # make sure the path is formatted pretty
        path = util.pretty_path(path, False, False)
        # parse the dir path for relative portions
        trailing = path.endswith('/')
        if path.startswith('/'):
            cur_dirs = ['/']
        else:
            cur_dirs = self.env('cwd').split('/')
        dirs = path.split('/')
        for dir in dirs:
            if dir == '' or dir == '.':
                # blanks can creep in on absolute paths, no worries
                continue
            rel_depth = 0
            if dir == '..':
                if not len(cur_dirs):
                    raise Exception("URI is out of bounds: \"%s\"." % (path))
                cur_dirs.pop()
            else:
                cur_dirs.append(dir)
        # always end up with an absolute path
        final_path = util.pretty_path('/'.join(cur_dirs), True, False)
        if trailing:
            final_path = final_path + '/'
        return final_path

    def run_cmd(self, cmd, params=None):
        """
        Run a command using the specified parameters.
        """
        if params is None:
            params = []
        if cmd == 'set':
            # break the array into the parts
            for str in params:
                pair = self.parse_param(str)
                param = pair.keys()[0]
                val = pair[param]
                if not (param in self.args):
                    raise Exception('Unrecognized parameter: "%s". Enter "%shelp" or "%sh" for help.' % (param, self._cmd_char, self._cmd_char))
                if param in ['invert', 'color', 'formatted', 'verbose', 'headers']:
                    # just so there is no confusion on these...
                    if val in ['1', 'true', 'True']:
                        val = True
                    elif val in ['0', 'false', 'False']:
                        val = False
                    self.args[param] = val
                elif param == 'edit_mode':
                    self.set_edit_mode(val)
                else:
                    raise Exception("Unrecognized configuration option: " + param + ".")
        elif cmd == 'env':
            sys.stdout.write('ENV:\n')
            if not params:
                params = self.env('vars').keys()
            for param in params:
                remove = False
                add = False
                if param.startswith('-='):
                    remove = True
                    param = param[2:]
                if param.startswith('+='):
                    add = True
                    param = param[2:]
                if add and param in self.data_store:
                    self.env('vars')[param] = self.data_store[param]
                if param in self.env('vars'):
                    value = self.env('vars')[param]
                    if remove:
                        sys.stdout.write('%s -= ' % (param))
                        del self.env('vars')[param]
                    elif add:
                        sys.stdout.write('%s +=' % (param))
                    else:
                        sys.stdout.write('%s = ' % (param))
                    sys.stdout.write(self.encode(value))
                    sys.stdout.write('\n')
        elif cmd == 'debug':
            import pdb
            pdb.set_trace()
        elif cmd == 'data':
            sys.stdout.write('DATA:\n')
            if not params:
                params = self.data_store.keys()
            for param in params:
                remove = False
                if param.startswith('-='):
                    remove = True
                    param = param[2:]
                if param in self.data_store:
                    value = self.data_store[param]
                    if remove:
                        sys.stdout.write('%s -= ' % (param))
                        del self.data_store[param]
                    else:
                        sys.stdout.write('%s = ' % (param))
                    sys.stdout.write(self.encode(value))
                    sys.stdout.write('\n')
        elif cmd == 'cd':
            path = ''
            if len(params):
                path = params[0]
            self.env('cwd', self.parse_path(path))
        elif cmd == 'config':
            dbg.pp(self.args)
            sys.stdout.write('\n')
        elif cmd == 'quit':
            return False
        elif cmd == 'help':
            self.print_help()
        elif cmd == 'sh':
            proc = subprocess.Popen(params)
        else:
            raise Exception('Unrecognized command: "%s". Enter "help" for help.' % (cmd))
        return True


if __name__ == '__main__':
    import rest_cli.dbg
    dbg.pretty_print(Shell())
