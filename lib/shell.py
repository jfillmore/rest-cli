#!/usr/bin/python -tt

"""Shell for interacting with a RESTful server."""

import re
from urllib import quote
import os
import sys
import os.path
import socket
os.environ['TERM'] = 'linux'
import readline
import shlex  # simple lexical anaysis for command line parsing
import subprocess  # for shell commands
try:
    import json
except:
    import simplejson
    json = simplejson


import util
import dbg
import client
from jsonx import jsonx


class JSONException(Exception):
    pass


class Shell:
    """Shell for interacting with REST client."""
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
        'histfile': None
    }
    # our default arguments
    default_args = {
        'color': sys.stdout.isatty(),
        'help': False,
        'formatted': True,
        'headers': {},
        'verbose': False,
        'url': 'https://localhost:443/',
        'shell': False
    }
    decode = json.JSONDecoder().decode  # JSON decoding

    def __init__(self, argv):
        self.last_rv = False
        self.env(
            'histfile',
            os.path.join(os.path.expanduser('~'), '.rest-cli_history')
        )
        # parse out our initial args
        self.args = self.parse_args(argv, self.default_args)
        self.client = client.RESTClient(self.args['url'])
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
        except KeyboardInterrupt, e:
            pass
        except EOFError, e:
            pass
        except ValueError, e:
            sys.stderr.write('! Input error: ' + str(e) + '\n')
            repeat = True
        except Exception as e:
            sys.stderr.write('! ' + str(e) + '\n')
            repeat = True
        if repeat:
            self.start(False)
        else:
            sys.stderr.write('\n')
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
        sys.stderr.write('''usage: rest-cli http-verb|command API [API_PARAMS] [ARGUMENTS]

ARGUMENTS
---------------------------------------------------------------------------

HTTP OPTIONS (each may be specified multiple times)
   -F, --file FILE          File to add to request.
   -Q, --query QUERY_DATA     Query data to include (e.g. foo=bar&food=yummy).
   -P, --post POST_DATA     Extra POST data to add to request.
   -H, --header HEADER      HTTP header (e.g. 'Foo: bar') .

OTHER OPTIONS (may also be set via 'set' command)
   -q, --quiet              Do not print API return response.
   -r, --raw                Don't format response data; return raw response.
   -v, --verbose            Print verbose debugging info to stderr.
   -i, --invert             Invert colors in formatted JSON responses.
   -C, --no-color           Do not color formatted JSON responses.
   -h, --help               This information.
   -u, --url URL            URL to the API location (default: https://localhost/).
   -j, --json STRING        Append JSON-encoded list to API parameters.
   -s, --shell              Shell mode for running multiple APIs within a session.
   -O, --oauth CK CS T TS   Authenticate via OAuth using the supplied consumer key, secret, token, and token secret.
   -x, --extract PATH       Parse JSON to only return requested data; may be repeated.
   -X, --exclude PATH       Exclude specified path from JSON data; may be repeated.

API PARAMS
---------------------------------------------------------------------------
Dictionaries can be created on demand using dot notation. Multiple params within the same dictionary will merge together. Values are always encoded as strings unless ":=" is used to assign the value.

   foo                      {"foo": true}
   !foo                     {"foo": false}
   foo=bar                  {"foo": "bar"}
   foo.bar=3 foo.bard=abc   {"foo": {"bar": "3", "bard": "abc"}}
   foo:='{"bar":3}'         {"foo": {"bar": 3}}
   foo.bar:=3.14            {"foo": {"bar": 3.14}}

JSON PATHS
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
   > FILE                   Write API response to specified file.
   >> FILE                  Append API response to specified file.

EXAMPLES:
---------------------------------------------------------------------------
    rest-cli -u https://foo.com/api -s
    > get site/foo.com -v
    > post site -j domain=foo.com
    > cd site/foo.com
    > get ./

''')

    def parse_args(self, expr, arg_slice=None):
        args = {
            'api': None,
            'verb': None,
            'api_args': {},
            'cmd_args': [],
            'headers': {},
            'json_extract': [],
            'json_exclude': [],
            'invert_color': False,
            'color': self.default_args['color'],
            'formatted': self.default_args['formatted'],
            'url': self.default_args['url'],
            'verbose': False,
            'stdout_redir': None,
            'redir_type': None,
            'shell': False,
            'query': [],
            'help': False,  # user just wanted some help
            'FILES': [],
            'POST': [],
            'oauth': {
                'consumer_key': None,
                'consumer_secret': None,
                'token': None,
                'token_secret': None
            }
        }
        if isinstance(expr, basestring):
            parts = shlex.split(expr)
        else:
            parts = expr  # already a list
        # check for any condensed parameters (e.g. -fr = -f, -r)
        old_parts = parts
        for i in range(0, len(parts)):
            if len(parts[i]) > 2 and parts[i][0] == '-' and parts[i][1] != '-':
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
            elif part == '-Q' or part == '--query':
                i += 1
                if i == len(parts):
                    raise Exception("Missing query name=value pair.")
                # make sure we have a valid pair
                if parts[i].find('=') == -1 or parts[i].find('&') != -1:
                    raise Exception("Invalid query name=value pair.")
                args['query'].append(parts[i])
            elif part == '-P' or part == '--post':
                i += 1
                if i == len(parts):
                    raise Exception("Missing POST name=value pair.")
                # make sure we have a valid pair
                if parts[i].find('=') == -1 or parts[i].find('&') != -1:
                    raise Exception("Invalid POST name=value pair.")
                args['POST'].append(parts[i])
                raise Exception("TODO: form-style post not implemented")
            elif part == '-i' or part == '--invert':
                args['invert_color'] = True
            elif part == '-C' or part == '--no-color':
                args['color'] = False
            elif part == '-v' or part == '--verbose':
                args['verbose'] = True
            elif part == '-O' or part == '--oauth':
                # the next 4 parameters are for oauth
                if i + 4 == len(parts):
                    raise Exception("Missing one of the following values for --oauth: consumer key, consumer secret, token, token secret.")
                next_params = [
                    'consumer_key', 'consumer_secret',
                    'token', 'token_secret'
                ]
                for ctr in range(0, 4):
                    args['oauth'][next_params[ctr]] = parts[i + ctr + 1]
                i += 4
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
                args['headers'][h_parts[0]] = h_parts[1]
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
                    sys.stderr.write('Invalid JSON:' + e.message)
                    raise e
                except Exception as e:
                    sys.stderr.write('Invalid JSON:' + e.message)
                    raise JSONException(e.message)
            elif part == '-r' or part == '--raw':
                args['formatted'] = False
            elif part == '--url' or part == '-u':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for URL.")
                args['url'] = parts[i]
            elif part == '-x' or part == '--extract':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for --extract.")
                args['json_extract'].append(parts[i])
            elif part == '-X' or part == '--exclude':
                i += 1
                if i == len(parts):
                    raise Exception("Missing value for --exclude.")
                args['json_exclude'].append(parts[i])
            else:
                # we always pick up the command/method first
                if args['verb'] is None:
                    args['verb'] = part.lower()
                    # process any aliases
                    if args['verb'] in self.method_aliases:
                        args['verb'] = self.method_aliases[args['verb']]
                elif args['verb'] in self.http_methods and args['api'] is None:
                    # collect the API -- unless this is a internal command
                    args['api'] = util.pretty_path(self.parse_path(part), False, False)
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
        # collect up the command parts
        args = self.parse_args(cli_cmd)
        # if we got oauth args we need to load in do so
        if args['oauth']['consumer_key']:
            self.client.load_oauth(args['oauth'])
        # not writing to a file by default
        file = None
        # run the command or API
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
                response = self.client.request(
                    args['verb'],
                    args['api'],
                    args['api_args'],
                    args['query'],
                    args['headers'],
                    args['verbose']
                )
                success = True
            except Exception as e:
                success = False
                response = e.message
            except socket.error as e:
                success = False
                response = unicode(e)
            self.last_rv = int(not success)
            # prep response redirection, since it worked
            if args['stdout_redir'] is not None:
                try:
                    file = open(args['stdout_redir'], args['redir_type'])
                except IOError as e:
                    sys.stderr.write('! Failed to write response: ' + e + '\n')
                    return True
        else:
            # run an internal command
            try:
                return self.run_cmd(args['verb'], args['cmd_args'])
            except Exception as e:
                response = e.message
                success = False
        # adjust the response object as requested
        if args['json_extract'] or args['json_exclude']:
            try:
                response = jsonx(
                    response,
                    extract=args['json_extract'],
                    exclude=args['json_exclude'],
                    raw=True
                )
            except:
                (exc_type, exc_msg, exc_tb) = sys.exc_info()
                sys.stderr.write('! %s\n' % exc_msg)
                return True
        self._print_response(
            success,
            response,
            formatted=args['formatted'],
            color=args['color'],
            invert_color=args['invert_color'],
            stdout_redir=args['stdout_redir'],
            redir_type=args['redir_type'],
            file=file
        )
        return True

    def _print_response(self, success, response, **args):
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
                    if isinstance(response, basestring):
                        if args.get('formatted'):
                            print response[0:512]
                            sys.stderr.write(
                                '# 512/%d bytes, use --raw|-r to see full output\n'
                                % len(response)
                            )
                        else:
                            print response
                    else:
                        if args.get('formatted'):
                            dbg.pretty_print(
                                response,
                                color=args.get('color'),
                                invert_color=args.get('invert_color')
                            )
                        else:
                            print json.dumps(response, indent=4, sort_keys=True)
        else:
            sys.stderr.write('! ' + response + '\n')

    def env(self, key, value=None):
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
        param_parts = str.split('=', 1)
        param = param_parts[0]
        # no value given? treat it as a boolean
        if len(param_parts) == 1:
            if param.startswith('!'):
                value = False
            else:
                value = True
            param = param.lstrip('!')
        else:
            value = param_parts.pop()
            # we we need to json-decode the value?
            if param.endswith(':'):  # e.g. 'foo:={"bar":42}'
                value = self.decode(value)
                param = param.rstrip(':')
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

    def run_cmd(self, cmd, params=[]):
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
        elif cmd == 'cd':
            path = ''
            if len(params):
                path = params[0]
            self.env('cwd', self.parse_path(path, False, False))
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
    import lib.dbg
    dbg.pretty_print(Shell())
