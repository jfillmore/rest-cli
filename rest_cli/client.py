#!/usr/bin/python -tt


"""Client for talking to a RESTful API server."""

from collections import namedtuple
import urllib
import urlparse
try:
    import json
except:
    import simplejson
    json = simplejson
import Cookie
import re
import sys
import dbg
import os
import base64
import hashlib
import socket
import time

from restkit import Resource, OAuthFilter
import restkit.oauth2 as oauth
from restkit.errors import (
    RequestError,
    RequestFailed,
    ResourceNotFound,
    Unauthorized
)

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
        # if set, an oauth authentication header will be included in each request
        self.oauth = None
        self.set_url(url)
        # TODO: python 2.7 supports an order tuple object we can use to
        # preserve order :)
        self.encode = json.JSONEncoder().encode
        self.decode = json.JSONDecoder().decode

    def parse_url(self, url):
        '''Cause urlparse just doesn't do it how I like it'''
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
        # let urlparse do the rest of the work on the path
        parsed = urlparse.urlparse('http://localhost/' + url)
        parts['path'] = parsed.path
        parts['params'] = parsed.params
        parts['query'] = parsed.query
        parts['fragment'] = parsed.fragment
        # force ourself to end in a slash -- well, maybe not...
        #if not self.path.endswith('/'):
        #    self.path = ''.join((self.path, '/'))
        return parts

    def set_url(self, url):
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

    def set_port(self, port):
        port = int(port)
        if port >= 0 and port <= 65535:
            self.url['port'] = port
        else:
            raise Exception('Invalid API service port: %s.' % port)

    def get(self, api, params, **opts):
        return self.request('GET', api, params, **opts)

    def post(self, api, params, **opts):
        return self.request('POST', api, params, **opts)

    def put(self, api, params, **opts):
        return self.request('PUT', api, params, **opts)

    def options(self, api, params, **opts):
        return self.request('OPTIONS', api, params, **opts)

    def delete(self, api, params, **opts):
        return self.request('DELETE', api, params, **opts)

    def build_query_obj(self, query):
        obj = urlparse.parse_qs(query)
        # all objects are lists by default, but it's probably more conventional to flatten single-item arrays
        new_obj = {}
        for key in obj:
            if len(obj[key]) == 1:
                new_obj[key] = obj[key][0]
            else:
                new_obj[key] = obj[key]
        return new_obj

    def build_query(self, params, topkey=''):
        '''Mimics the behaviour of http_build_query PHP function'''
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
        if not query2:
            return query1
        return '&'.join([query1, query2])

    def merge_url_query(self, url, query):
        if url.find('?') >= 0:
            url, existing_query = url.split('?', 1)
            query = self.merge_query(existing_query, query)
        return '?'.join((url, query)).rstrip('?')

    def get_header(self, headers, header, value=None):
        for key in headers:
            if key.lower() == header.lower():
                if value is None:
                    return headers[key]
                else:
                    return headers[key] == value
        return None

    def _prep_request(self, api_url, params=None):
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
        return Resource(api_url, filters=filters)

    def _build_url(self, api, query):
        path = util.pretty_path(
            '/'.join(['', self.url['path'], api]),
            True,
            False
        )
        url = '%s://%s:%s%s' % (
            self.url['scheme'], self.url['hostname'], self.url['port'], path
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

    def request(self, method, api, params=None, query=None, headers=None,
                verbose=False, full=False):
        # normalize the API parameters
        if method is None or method == '':
            method = 'get'
        method = method.lower()
        if api == '' or api is None:
            api = '/'
        if params is None:
            params = {}
        if type(query) == list:
            query = '&'.join(query)
        elif type(query) == dict:
            query = self.build_query(query)
        if api.find('?') >= 0:
            api, api_query = api.split('?', 1)
            # TODO: tests whether query args need to be in the URL or params for oauth signing
            query = self.merge_query(api_query, query)
        # merge in base URL params
        url, query = self._build_url(api, query)
        # trust that reskit will do quoting...
        resource = self._prep_request(url, params)
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
            request_args['params_dict'] = query_obj
            payload = ''
        else:
            if self.get_header(headers, 'Content-Type', 'application/json'):
                payload = self.encode(params)
            else:
                # not sure >how< to encode, so good 'nuff for now
                payload = urllib.urlencode(params)
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
        if not content_type.startswith("application/json"):
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
                    method.upper(), api, response.meta.status
                ),
                response,
            )
        if full:
            return response
        return decoded

if __name__ == '__main__':
    dbg.pretty_print(RESTClient())
