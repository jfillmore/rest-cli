#!/usr/bin/python -tt

# TODO:
# - JSON body for GET requests


"""Client for talking to a RESTful server. Maybe just even a regular web server."""

from collections import namedtuple
import Cookie
import base64
import dbg
import hashlib
import os
import re
import socket
import sys
import time
import urllib
import urlparse
try:
    import json
except:
    import simplejson
    json = simplejson

from restkit import Resource, OAuthFilter
from restkit.errors import (
    RequestError,
    RequestFailed,
    ResourceNotFound,
    Unauthorized
)
import restkit.oauth2 as oauth
from restkit import BasicAuth

import util


Response = namedtuple('Response', ['meta', 'decoded', 'raw'])


class APIException(Exception):

    def __init__(self, error, response):
        self.response = response
        super(APIException, self).__init__(error)


class RESTClient:

    """Client for talking to a RESTful server."""

    def __init__(self, url='localhost'):
        # the base URL information for construction API requests
        self.url = None
        self.cookies = {}  # session cookie cache
        # if set, an oauth/basic authentication header will be included in each request
        self.oauth = None
        self.basic_auth = None
        self.set_url(url)
        # TODO: python 2.7 supports an order tuple object we can use to preserve order :)
        self.encode = json.JSONEncoder().encode
        self.decode = json.JSONDecoder().decode

    def _prep_request(self, api_url, basic_auth=None):
        filters = []
        if self.oauth:
            consumer = oauth.Consumer(
                key=self.oauth['consumer_key'],
                secret=self.oauth['consumer_secret']
            )
            token = oauth.Token(
                key=self.oauth['token'],
                secret=self.oauth['token_secret']
            )
            oauth_filter = OAuthFilter('*', consumer, token)
            filters.append(oauth_filter)
        elif basic_auth:
            auth_parts = basic_auth.split(':', 1)
            filters.append(BasicAuth(auth_parts[0], auth_parts[1]))
        elif self.basic_auth:
            filters.append(BasicAuth(self.basic_auth['username'], self.basic_auth['password']))
        return Resource(api_url, filters=filters)

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
        '''Parses a URL into its components. Allows as little information as possible (e.g. just a port, just a path), defaulting to http://localhost:80/.'''
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
        parsed = urlparse.urlparse('http://localhost/' + url)
        parts['path'] = parsed.path
        parts['params'] = parsed.params
        parts['query'] = parsed.query
        parts['fragment'] = parsed.fragment
        return parts

    def set_url(self, url):
        '''Sets the base URL for requests. Assumes http://localhost by default.'''
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

    def load_oauth(self, creds):
        '''Sets OAuth keys to be used for each request. Can be set to None to stop using OAuth.'''
        keys = [
            'consumer_key', 'consumer_secret',
            'token', 'token_secret'
        ]
        if creds is None:
            self.oauth = None
        else:
            for item in keys:
                if not creds[item]:
                    raise Exception("Missing value for OAuth key '%s'." %
                                    (item))
            self.oauth = creds

    def load_basic_auth(self, username=None, password=None):
        if username is not None and password is not None:
            self.basic_auth = {'username': username, 'password': password}
        else:
            self.basic_auth = None

    def set_port(self, port):
        '''Set the port that will be used for requests.'''
        port = int(port)
        if port >= 0 and port <= 65535:
            self.url['port'] = port
        else:
            raise Exception('Invalid API service port: %s.' % port)

    def get(self, path, params=None, **opts):
        '''Perform a GET request with the provided query string parameters. If the base URL and/or path contain query string parameters they will all be merged.'''
        return self.request('GET', path, params, **opts)

    def post(self, path, params=None, **opts):
        '''Perform a POST request with the supplied parameters as the payload. Defaults to JSON encoding.'''
        return self.request('POST', path, params, **opts)

    def put(self, path, params=None, **opts):
        '''Perform a PUT request with the supplied parameters as the payload. Defaults to JSON encoding.'''
        return self.request('PUT', path, params, **opts)

    def options(self, path, params=None, **opts):
        '''Perform a OPTIONS request with the supplied parameters as the payload. Defaults to JSON encoding.'''
        return self.request('OPTIONS', path, params, **opts)

    def delete(self, path, params=None, **opts):
        '''Perform a DELETE request with the supplied parameters as the payload. Defaults to JSON encoding.'''
        return self.request('DELETE', path, params, **opts)

    def request(self, method, path, params=None, query=None, headers=None,
                verbose=False, full=False, basic_auth=None):
        # normalize the API parameters
        if method is None or method == '':
            method = 'get'
        method = method.lower()
        if path == '' or path is None:
            path = '/'
        if params is None:
            params = {}
        if type(query) == list:
            query = '&'.join(query)
        elif type(query) == dict:
            query = self.build_query(query)
        if path.find('?') >= 0:
            path, api_query = path.split('?', 1)
            # TODO: tests whether query args need to be in the URL or params for oauth signing
            query = self.merge_query(api_query, query)
        # merge in base URL params
        url, query = self._build_url(path, query)
        # trust that reskit will do quoting...
        resource = self._prep_request(url, basic_auth)
        # prep the rest of the request args
        headers = headers if isinstance(headers, dict) else {}
        # set the header unless we have a content-type already specified
        if not self.get_header(headers, 'Content-Type') and method != 'get':
            headers['Content-Type'] = 'application/json'
        headers['Accept'] = 'application/json'
        request_args = {
            'headers': []
        }
        for hdr_name in headers:
            hdr_value = headers[hdr_name]
            request_args['headers'].append((hdr_name, hdr_value))
        for name in self.cookies:
            request_args['headers'].append(('Cookie', '='.join([name, self.cookies[name]])))
        if method == 'get':
            # convert the query to an obj for final use
            query_obj = self.build_query_obj(query)
            if params:
                query_obj.update(params)
            if query_obj:
                request_args['params_dict'] = query_obj
            payload = ''
        else:
            if self.get_header(headers, 'Content-Type', 'application/json'):
                payload = self.encode(params)
            elif self.get_header(headers, 'Content-Type', 'application/x-www-form-urlencoded'):
                payload = urllib.urlencode(params)
            else:
                # assume its already been encoded
                payload = params
            request_args['payload'] = payload
        # fire away!
        if verbose:
            sys.stderr.write(
                '# Request: %s %s\n' % (method.upper(), url)
            )
            if payload:
                sys.stderr.write('# Request Body: %s\n' % payload)
            elif 'params_dict' in request_args:
                sys.stderr.write('# Request Query: %s\n' % request_args['params_dict'])
            sys.stderr.write('# Request Headers: %s\n' % str(headers))
            if self.oauth:
                sys.stderr.write('# Oauth consumer key: %s\n' % self.oauth['consumer_key'])
            if self.cookies:
                sys.stderr.write('# Request Cookies: %s\n' % str(self.cookies))
        try:
            response = getattr(resource, method)(**request_args)
            response_data = response.body_string()
        except RequestFailed as e:
            response = e.response
            response_data = e.message
        except ResourceNotFound as e:
            response = e.response
            response_data = e.message
        except Unauthorized as e:
            response = e.response
            response_data = e.message
        # see if we get a cookie back; note that we ignore the path
        for hdr_name, hdr_value in response.headerslist:
            if hdr_name.lower() == 'set-cookie':
                cookies = Cookie.BaseCookie(hdr_value)
                for name in cookies:
                    self.cookies[name] = cookies[name].value
        if verbose:
            sys.stderr.write(
                '# Response Status: %s\n# Response Headers: %s\n' % (
                    response.status, self.encode(response.headers)
                )
            )
        content_type = response.headers.get('Content-Type')
        if not content_type or not content_type.startswith("application/json"):
            decoded = response_data
        else:
            try:
                decoded = self.decode(response_data)
            except:
                raise Exception('Failed to decode API response\n' + response_data)
        response = Response(meta=response, decoded=decoded, raw=response_data)
        if response.meta.status_int < 200 or response.meta.status_int >= 400:
            raise APIException(
                '"%s %s" failed (%s)' % (
                    method.upper(), path, response.meta.status
                ),
                response,
            )
        if full:
            return response
        return decoded

    def build_query_obj(self, query, keep_blanks=True):
        '''Translates a query string into an object. If multiple keys are used the values will be contained in an array.'''
        obj = urlparse.parse_qs(query, keep_blank_values=keep_blanks)
        # all objects are lists by default, but it's probably more conventional to flatten single-item arrays
        new_obj = {}
        for key in obj:
            if len(obj[key]) == 1:
                new_obj[key] = obj[key][0]
            else:
                new_obj[key] = obj[key]
        return new_obj

    def build_query(self, params, topkey=''):
        '''Mimics the behaviour of http_build_query PHP function (e.g. arrays will be encoded as foo[0]=bar, booleans as 0/1).'''
        if len(params) == 0:
            return ""
        result = ""
        # is a dictionary?
        if type(params) is dict:
            for key in params.keys():
                newkey = urllib.quote(key)
                if topkey != '':
                    newkey = topkey + urllib.quote('[' + key + ']')
                if type(params[key]) is dict:
                    result += self.build_query(params[key], newkey)
                elif type(params[key]) is list:
                    i = 0
                    for val in params[key]:
                        result += newkey + urllib.quote('[' + str(i) + ']') \
                            + "=" + urllib.quote(str(val)) + "&"
                        i = i + 1
                # boolean should have special treatment as well
                elif type(params[key]) is bool:
                    result += newkey + "=" + urllib.quote(str(int(params[key]))) + "&"
                # assume string (integers and floats work well)
                else:
                    result += newkey + "=" + urllib.quote(str(params[key])) + "&"
        # remove the last '&'
        if result and topkey == '' and result[-1] == '&':
            result = result[:-1]
        return result

    def merge_query(self, query1, query2=None):
        '''Merge two query strings together. Neither query string should contain the '?' delimiter.'''
        if not query2:
            return query1
        return '&'.join([query1, query2])

    def merge_url_query(self, url, query):
        '''Update a URL to add or append a query string.'''
        if url.find('?') >= 0:
            url, existing_query = url.split('?', 1)
            query = self.merge_query(existing_query, query)
        return '?'.join((url, query)).rstrip('?')

    def get_header(self, headers, header, value=None):
        '''Read a header from the given list (ignoring case) and return the value. Returns None if not found, or optionally the value given.'''
        for key in headers:
            if key.lower() == header.lower():
                if value is None:
                    return headers[key]
                else:
                    return headers[key] == value
        return None


if __name__ == '__main__':
    dbg.pretty_print(RESTClient())
