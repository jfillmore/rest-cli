#!/usr/bin/python -tt

# TODO:
# - JSON body for GET requests


"""
Client for talking to a RESTful server. Maybe just even a regular web server.
"""

from collections import namedtuple
import base64
import http.cookies
import json
import re
import ssl
import sys
import time
import urllib

from . import dbg
from . import util


Response = namedtuple('Response', ['obj', 'decoded', 'data'])


class ApiException(Exception):
    def __init__(self, error, response):
        self.response = response
        super().__init__(error)


class RESTClient:
    """
    Client for talking to a RESTful server.
    """

    def __init__(self, url='localhost', insecure=False):
        # the base URL information for construction API requests
        self.url = None
        self.cookies = {}  # session cookie cache
        # if set, an oauth/basic authentication header will be included in each request
        self.oauth = None
        self.basic_auth = None
        self.set_url(url)
        self.ssl_ctx = ssl.create_default_context()
        if insecure:
            self.ssl_ctx.check_hostname = False
            self.ssl_ctx.verify_mode = ssl.CERT_NONE

    def _build_url(self, path, query):
        path = util.pretty_path(
            '/'.join(['', self.url['path'], path]),
            True,
            False
        )
        port = self.url['port']
        if port == 80 or port == 443:
            port = ''
        else:
            port = ':' + str(port)
        url = '%s://%s%s%s' % (
            self.url['scheme'], self.url['hostname'], port, path
        )
        # has the base URL been set to include query params?
        if self.url['query']:
            url = self.merge_url_query(url, self.url['query'])
        # add in manually passed query args
        if query:
            url = self.merge_url_query(url, query)
        # with everything merged into the URL, do a final split
        if url.find('?') >= 0:
            (url, query) = url.split('?', 1)
        else:
            query = ''
        # return the full URL, as well as our final query
        return url, query

    def parse_url(self, url):
        """
        Parses a URL into its components. Allows as little information as possible (e.g. just a port, just a path), defaulting to http://localhost:80/.
        """
        # urlparse just doesn't do it the "right" way...
        # check for protocol and strip it off if found
        parts = {
            'scheme': None,
            'hostname': None,
            'port': None,
            'path': None,
            'params': None,
            'query': None,
            'fragment': None
        }
        # parse out the scheme, if present
        if re.match('^\w+://', url):
            (scheme, url) = url.split('://', 1)
            parts['scheme'] = scheme.lower()
        else:
            parts['scheme'] = 'http'
        # check for a path
        if url.find('/') == -1:
            hostname = url
            url = ''
        else:
            (hostname, url) = url.split('/', 1)
        # do we have a port in the hostname?
        if hostname.find(':') >= 0:
            # chop out the port
            hostname, parts['port'] = hostname.split(':', 1)
        if not hostname:
            hostname = 'localhost'
        parts['hostname'] = hostname.lower()
        # let urlparse do the rest of the work on the path w/ a fake domain
        parsed = urllib.parse.urlparse('http://localhost/' + url)
        parts['path'] = parsed.path
        parts['params'] = parsed.params
        parts['query'] = parsed.query
        parts['fragment'] = parsed.fragment
        return parts

    def set_url(self, url):
        """
        Sets the base URL for requests. Assumes http://localhost by default.
        """
        if url == '':
            raise Exception('Invalid API URL: %s.' % url)
        url = self.parse_url(url)
        self.url = url
        if url['scheme'] != 'http' and url['scheme'] != 'https':
            raise Exception('Only HTTP and HTTPS are supported protocols.')
        if url['port']:
            self.set_port(url['port'])
        else:
            if url['scheme'] == 'https':
                self.set_port(443)
            else:
                self.set_port(80)

    def load_basic_auth(self, username=None, password=None):
        if username is not None and password is not None:
            self.basic_auth = {'username': username, 'password': password}
        else:
            self.basic_auth = None

    def set_port(self, port):
        """
        Set the port that will be used for requests.
        """
        port = int(port)
        if port >= 0 and port <= 65535:
            self.url['port'] = port
        else:
            raise Exception('Invalid API service port: %s.' % port)

    def get(self, path, params=None, **opts):
        """
        Perform a GET request with the provided query string parameters. If the
        base URL and/or path contain query string parameters they will all be
        merged.
        """
        return self.request('GET', path, params, **opts)

    def post(self, path, params=None, **opts):
        """
        Perform a POST request with the supplied parameters as the payload.
        Defaults to JSON encoding.
        """
        return self.request('POST', path, params, **opts)

    def patch(self, path, params=None, **opts):
        """
        Perform a PATCH request with the supplied parameters as the payload.
        Defaults to JSON encoding.
        """
        return self.request('PATCH', path, params, **opts)

    def put(self, path, params=None, **opts):
        """
        Perform a PUT request with the supplied parameters as the payload.
        Defaults to JSON encoding.
        """
        return self.request('PUT', path, params, **opts)

    def options(self, path, params=None, **opts):
        """
        Perform a OPTIONS request with the supplied parameters as the payload.
        Defaults to JSON encoding.
        """
        return self.request('OPTIONS', path, params, **opts)

    def delete(self, path, params=None, **opts):
        """
        Perform a DELETE request with the supplied parameters as the payload.
        Defaults to JSON encoding.
        """
        return self.request('DELETE', path, params, **opts)

    def request(
            self, method, path, params=None, query=None, headers=None,
            verbose=False, full=False, basic_auth=None, pre_formatted_body=False,
        ):
        # normalize the API parameters
        if method is None or method == '':
            method = 'get'
        method = method.upper()
        if path == '' or path is None:
            path = '/'
        if params is None:
            params = {}
        if isinstance(query, list):
            query = '&'.join(query)
        elif isinstance(query, dict):
            query = self.build_query(query)
        # TODO: allow params to be in the request body (e.g. like ElasticSearch prefers)
        if method == 'GET' and params:
            query = self.merge_query(self.build_query(params), query)
        url, query = self._build_url(path, query)
        if query:
            url = '?'.join([url, query])

        request_args = {
            'headers': {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }
        }

        # request headers (misc, cookies, auth, etc)
        if headers:
            request_args['headers'].update(headers)
        cookies = []
        for name in self.cookies:
            cookie.append('='.join([name, self.cookies[name]]))
        if cookies:
            request_args['headers']['Cookie'] = '&'.join(cookies)
        if basic_auth or self.basic_auth:
            if not basic_auth:
                basic_auth = ':'.join([
                    self.basic_auth['username'],
                    self.basic_auth['password'],
                ])
            auth_header ='Basic ' + base64.b64encode(basic_auth)
            request_args['headers']['Authorization'] = auth_header

        # request body
        if method == 'GET':
            body = ''
        else:
            if pre_formatted_body:
                body = params
            else:
                if self.get_header(request_args['headers'], 'Content-Type', 'application/json'):
                    body = json.dumps(params).encode('utf-8')
                elif self.get_header(request_args['headers'], 'Content-Type', 'application/x-www-form-urlencoded'):
                    body = urllib.parse.urlencode(params)
                else:
                    # assume its already been encoded
                    body = params
            request_args['data'] = body

        # fire away!
        if verbose:
            dbg.log(
                'Request:',
                data=' %s %s' % (method.upper(), url),
                data_inline=True
            )
            if body:
                dbg.log('Request Body: ', data=body, data_inline=True)
            if request_args['headers']:
                dbg.log('Request Headers:', data=request_args['headers'])
            if self.cookies:
                dbg.log('Request Cookies:', data=self.cookies)
        request = urllib.request.Request(url, **request_args)
        try:
            response = urllib.request.urlopen(request, context=self.ssl_ctx)
        except urllib.request.HTTPError as error_resp:
            response = error_resp
        response_data = response.read().decode('utf-8')

        # see if we get a cookie back; note that we ignore the path
        for hdr_name, hdr_value in response.headers.items():
            if hdr_name.lower() == 'set-cookie':
                cookies = http.cookies.BaseCookie(hdr_value)
                for name in cookies:
                    self.cookies[name] = cookies[name].value
        if verbose:
            dbg.log('Response Status: ', data=response.status, data_inline=True)
            dbg.log('Response Headers:', data={
                    name: val
                    for name, val in response.headers.items()
                }
            )
        content_type = response.headers.get('Content-Type')
        if not content_type or not content_type.startswith("application/json"):
            decoded = response_data
        else:
            try:
                decoded = json.loads(response_data)
            except:
                raise Exception('Failed to decode API response\n' + response_data)
        response = Response(obj=response, decoded=decoded, data=response_data)
        if response.obj.status < 200 or response.obj.status >= 400:
            raise ApiException(
                '"%s %s" failed (%s)' % (
                    method, path, response.obj.status
                ),
                response,
            )
        if full:
            return response
        return decoded

    @classmethod
    def build_query_obj(cls, query, keep_blanks=True):
        """
        Translates a query string into an object. If multiple keys are used the
        values will be contained in an array.
        """
        obj = urllib.parse.parse_qs(query, keep_blank_values=keep_blanks)
        # all objects are lists by default, but it's probably more conventional to flatten single-item arrays
        new_obj = {}
        for key in obj:
            if len(obj[key]) == 1:
                new_obj[key] = obj[key][0]
            else:
                new_obj[key] = obj[key]
        return new_obj

    @classmethod
    def build_query(cls, params, topkey=''):
        """
        Mimics the behaviour of http_build_query PHP function (e.g. arrays will
        be encoded as foo[0]=bar, booleans as 0/1).
        """
        if len(params) == 0:
            return ""
        result = ""
        # is a dictionary?
        if isinstance(params, dict):
            for key in params.keys():
                newkey = urllib.quote(key)
                if topkey != '':
                    newkey = topkey + urllib.quote('[' + key + ']')
                if isinstance(params[key], dict):
                    result += cls.build_query(params[key], newkey)
                elif isinstance(params[key], list):
                    i = 0
                    for val in params[key]:
                        result += newkey + urllib.quote('[' + str(i) + ']') \
                            + "=" + urllib.quote(str(val)) + "&"
                        i = i + 1
                # boolean should have special treatment as well
                elif isinstance(params[key], bool):
                    result += newkey + "=" + urllib.quote(str(int(params[key]))) + "&"
                # assume string (integers and floats work well)
                else:
                    result += newkey + "=" + urllib.quote(str(params[key])) + "&"
        # remove the last '&'
        if result and topkey == '' and result[-1] == '&':
            result = result[:-1]
        return result

    @classmethod
    def merge_query(cls, query1: str, query2: str = None):
        """
        Merge two query strings together. Discards any leading '?' characters.
        """
        if query1.startswith('?'):
            query1 = query1[1:]
        if not query2:
            return query1
        elif query2.startswith('?'):
            query2 = query2[1:]
        return '&'.join([query1, query2])

    @classmethod
    def merge_url_query(cls, url: str, query: str):
        """
        Update a URL to add or append a query string.
        """
        if url.find('?') >= 0:
            url, existing_query = url.split('?', 1)
            query = cls.merge_query(existing_query, query)
        return '?'.join((url, query)).rstrip('?')

    @classmethod
    def get_header(cls, headers: dict, header: str, value=None):
        """
        Read a header from the given list (ignoring case) and return the value.
        Returns None if not found, or optionally the value given.
        """
        for key in headers:
            if key.lower() == header.lower():
                if value is None:
                    return headers[key]
                else:
                    return headers[key] == value
        return None


if __name__ == '__main__':
    dbg.pretty_print(RESTClient())
