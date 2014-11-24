#!/usr/bin/python -tt


"""Client for talking to a RESTful API server."""

import urllib
from urlparse import urlparse
import httplib
try:
    import json
except:
    import simplejson
    json = simplejson
import re
import sys
import dbg
import os
import base64
import hashlib
import socket
import time

import util


class RESTClient:

    """Client for talking to a RESTful server."""

    def __init__(self, url='localhost'):
        self.http = None
        self.url = None
        self.use_https = False
        # if set, an oauth authentication header will be included in each request
        self.oauth = None

        # tempfile.NamedTemporaryFile()
        # setup cookie jar
        self.cookie_file = os.path.expanduser('~/.rest-cli_cookies')
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
        parsed = urlparse('http://localhost/' + url)
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
        self.set_https(url['scheme'] == 'https')
        if url['port']:
            self.set_port(url['port'])
        else:
            if self.use_https:
                self.set_port(443)
            else:
                self.set_port(80)
        http_args = self.url['hostname'], self.url['port']
        if self.use_https:
            self.http = httplib.HTTPSConnection(*http_args)
        else:
            self.http = httplib.HTTPConnection(*http_args)
        self.http.cookies = False

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

    def set_https(self, secure=True):
        if secure:
            self.use_https = True
        else:
            self.use_https = False

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

    def get_oauth_header(self, method, url, params=None):
        import oauth2
        consumer = oauth2.Consumer(
            key=self.oauth['consumer_key'],
            secret=self.oauth['consumer_secret']
        )
        token = oauth2.Token(
            key=self.oauth['token'],
            secret=self.oauth['token_secret']
        )
        oauth_params = {
            'oauth_timestamp': int(time.time()),
            'oauth_version': '1.0',
            'oauth_nonce': 1,
            'oauth_consumer_key': consumer.key,
            'oauth_token': token.key
        }
        params = dict(params.items() + oauth_params.items()) \
            if params else oauth_params
        request = oauth2.Request(
            method=method, url=url, parameters=params)
        request.sign_request(
            oauth2.SignatureMethod_HMAC_SHA1(), consumer, token)
        return request.to_header()['Authorization']

    def merge_query(self, url, query):
        index = url.find('?')
        if index >= 0:
            url, existing_query = url.split('?', 1)
            query = '&'.join((existing_query, query))
        return '?'.join((url, query)).rstrip('?')

    def get_header(self, headers, header, value=None):
        for key in headers:
            if key.lower() == header.lower():
                if value is None:
                    return headers[key]
                else:
                    return headers[key] == value
        return None

    def request(self, method, api, params=None, query=None, headers=None,
                verbose=False, meta=False
                ):
        '''REST API invoker'''
        # check and prep the data
        if method is None or method == '':
            method = 'GET'
        method = method.upper()
        if api == '' or api is None:
            api = '/'
        if params is None:
            params = {}
        if api.find('?') >= 0:
            api, api_query = api.split('?', 1)
        api = urllib.quote(api)
        http = self.http
        # figure out the URL
        headers = headers if isinstance(headers, dict) else {}
        if not self.get_header(headers, 'Content-Type') and method != 'GET':
            headers['Content-Type'] = 'application/json'
        headers['Accept'] = 'application/json'
        path = util.pretty_path('/'.join(('', self.url['path'], api)), True, False)
        url = '%s://%s%s' % (
            self.url['scheme'], self.url['hostname'], path
        )
        # add a header for oauth2 if needed
        if self.oauth:
            headers['Authorization'] = self.get_oauth_header(method, url, params)
        # were extra query params passed in explicitly?
        if query:
            url = self.merge_query(url, query)
        # has the base URL been set to include query params?
        if self.url['query']:
            url = self.merge_query(url, self.url['query'])
        if method == 'GET':
            get_params = self.build_query(params)
            url = self.merge_query(url, get_params)
            data = ''
        else:
            if self.get_header(headers, 'Content-Type', 'application/json'):
                data = self.encode(params)
            else:
                data = urllib.urlencode(params)
        # fire away
        if verbose:
            sys.stderr.write(
                '# Request: %s %s, body: "%s"\n' % (
                    method, url, data
                )
            )
            sys.stderr.write('# Request Headers: %s\n' % str(headers))
            if http.cookies:
                sys.stderr.write(' # Request Cookies: %s\n' % str(http.cookies))
        # be willing to try again if the socket got closed on us (e.g. timeout)
        tries = 0
        max_tries = 3
        response = None
        last_error = None
        while tries < max_tries and response is None:
            tries += 1
            try:
                # start the request
                http.putrequest(method, url)
                # send our headers
                for hdr, value in headers.iteritems():
                    http.putheader(hdr, value)
                # and our cookies too!
                if http.cookies:
                    [http.putheader('Cookie', value) for value in http.cookies]
                # write the body
                if data:
                    body_len = len(data)
                    if body_len:
                        http.putheader('Content-Length', str(body_len))
                http.endheaders()
                if data:
                    http.send(data)
                # get our response back from the server and parse
                response = http.getresponse()
            except socket.error as e:
                last_error = e
                http.connect()
            except Exception as e:
                last_error = e
                http.close()
        if response is None:
            raise Exception('HTTP request failed and could not be retried: %s' % last_error)
        # see if we get a cookie back
        response_headers = str(response.msg).split('\n')
        # note that we ignore the path
        cookies = [c.split(': ')[1].split('; ')[0]
                   for c in response_headers if c.startswith('Set-Cookie: ')]
        if cookies:
            http.cookies = cookies
        if verbose:
            sys.stderr.write(
                '# Response Status: %s %s\n# Response Headers: %s\n' %
                (response.status, response.reason, self.encode(
                    str(response.msg).strip().split('\r\n')
                ))
            )
        content_type = response.getheader('Content-Type') or ''
        response_data = response.read()
        if not content_type.startswith("application/json"):
            payload = response_data
        else:
            try:
                payload = self.decode(response_data)
            except:
                raise Exception('Failed to decode API response\n' + response_data)
        if response.status < 200 or response.status >= 300:
            raise Exception('API "%s" failed (%d %s)\n%s' %
                            (urllib.unquote(api), response.status,
                             response.reason, response_data))
        return payload

if __name__ == '__main__':
    dbg.pretty_print(RESTClient())
