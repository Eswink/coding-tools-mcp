"""Standalone, fixed-origin metadata GET worker; no credentials are discovered.

Only the trusted parent supplies a token over a private length-framed pipe.
The parent, not idle socket timeouts, owns absolute deadlines and termination.
"""
from __future__ import annotations

import http.client
import json
import math
import re
import ssl
import struct
import sys

ORIGIN = 'https://api.github.com'
BASE = '/repos/Eswink/coding-tools-mcp'
MAX_BODY = 1024 * 1024
MAX_FRAME = 2 * MAX_BODY
MAX_REQUEST = 16384
MAX_VALUE_STRING = 65536
ERROR_CODES = frozenset({
    'invalid_operation', 'invalid_arguments', 'invalid_token', 'unsupported_platform',
    'request_limit', 'response_limit', 'aggregate_limit', 'session_timeout',
    'request_timeout', 'invalid_json', 'duplicate_json_key', 'nonfinite_json',
    'json_depth_limit', 'json_object_limit', 'json_array_limit', 'json_string_limit',
    'json_integer_limit', 'invalid_response_shape', 'invalid_headers', 'invalid_link',
    'unauthorized', 'forbidden', 'not_found_or_not_visible', 'rate_limited',
    'server_error', 'unexpected_status', 'redirect_rejected', 'tls_failure',
    'transport_failure', 'close_failure', 'worker_start_failed', 'worker_failed',
    'invalid_ipc', 'adapter_closed', 'concurrent_request', 'cleanup_uncertain',
})


class MetadataAPIError(ValueError):
    """Only a fixed diagnostic code may escape a transport operation."""

    def __init__(self, code):
        self.code = code if type(code) is str and code in ERROR_CODES else 'worker_failed'
        super().__init__(self.code)


def require(ok, code):
    if not ok:
        raise MetadataAPIError(code)


def positive(value):
    require(type(value) is int and 0 < value < 2**63, 'invalid_arguments')
    return value


def valid_token(token):
    require(type(token) is str and 1 <= len(token) <= 4096
            and all(33 <= ord(char) <= 126 for char in token), 'invalid_token')


def route(operation, arguments):
    """Validate exact typed arguments and construct the sole permitted routes."""
    specs = {
        'repository': (), 'ref': ('branch',), 'commit': ('sha',), 'tree': ('sha',),
        'workflow': ('role',), 'runs': ('workflow_id', 'sha', 'page'),
        'run': ('run_id',), 'jobs': ('run_id', 'attempt', 'page'),
        'pr': (), 'reviews': ('page',), 'commits': ('page',),
    }
    require(type(operation) is str and operation in specs, 'invalid_operation')
    require(type(arguments) is dict and set(arguments) == set(specs[operation]),
            'invalid_arguments')
    for key, value in arguments.items():
        if key in {'workflow_id', 'run_id', 'attempt', 'page'}:
            positive(value)
        if key == 'page':
            require(value <= 10, 'invalid_arguments')
        if key == 'sha':
            require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value),
                    'invalid_arguments')
    if operation == 'ref':
        branch = arguments['branch']
        require(type(branch) is str and re.fullmatch(
            r'refs/heads/(?:feat/rc-pretag-metadata-1dfe|release/'
            r'full-rc-candidate-[A-Za-z0-9][A-Za-z0-9._-]{0,79})', branch)
            and '..' not in branch and not branch.endswith('.'), 'invalid_arguments')
        return BASE + '/git/ref/' + branch[len('refs/'):]
    if operation in {'commit', 'tree'}:
        component = 'commits' if operation == 'commit' else 'trees'
        return BASE + '/git/' + component + '/' + arguments['sha']
    if operation == 'workflow':
        names = {'integration': 'dot-rc-integration.yml', 'final': 'final-rc-packages.yml'}
        role = arguments['role']
        require(type(role) is str and role in names, 'invalid_arguments')
        return BASE + '/actions/workflows/' + names[role]
    if operation == 'runs':
        return (BASE + '/actions/workflows/' + str(arguments['workflow_id'])
                + '/runs?head_sha=' + arguments['sha']
                + '&per_page=100&page=' + str(arguments['page']))
    if operation in {'run', 'jobs'}:
        path = BASE + '/actions/runs/' + str(arguments['run_id'])
        if operation == 'jobs':
            path += ('/attempts/' + str(arguments['attempt']) + '/jobs?per_page=100&page='
                     + str(arguments['page']))
        return path
    if operation == 'repository':
        return BASE
    path = BASE + '/pulls/36'
    if operation in {'reviews', 'commits'}:
        path += '/' + operation + '?per_page=100&page=' + str(arguments['page'])
    return path


def link_relations(operation, arguments, link):
    """Accept canonical, same-operation page hints, never destinations to follow."""
    if link is None:
        return {}
    require('page' in arguments and type(link) is str and 0 < len(link) <= 4096
            and all(32 <= ord(char) <= 126 for char in link),
            'invalid_link')
    result = {}
    parts = link.split(',')
    require(len(parts) <= 4, 'invalid_link')
    current = arguments['page']
    for part in parts:
        match = re.fullmatch(r'\s*<([^<>\s]+)>; rel="(next|prev|first|last)"\s*', part)
        require(match is not None, 'invalid_link')
        url, relation = match.groups()
        require(relation not in result, 'invalid_link')
        page_match = re.search(r'[?&]page=([1-9][0-9]?)$', url)
        require(page_match is not None, 'invalid_link')
        page = int(page_match.group(1))
        expected = dict(arguments, page=page)
        require(1 <= page <= 10 and url == ORIGIN + route(operation, expected),
                'invalid_link')
        require((relation != 'next' or page == current + 1)
                and (relation != 'prev' or page == current - 1)
                and (relation != 'first' or page == 1)
                and (relation != 'last' or page >= current), 'invalid_link')
        result[relation] = page
    require('next' not in result or 'last' not in result or result['next'] <= result['last'],
            'invalid_link')
    require('prev' not in result or 'first' not in result or result['prev'] >= result['first'],
            'invalid_link')
    return result


def parse_json(raw, *, response=True):
    require(type(raw) is bytes and len(raw) <= (MAX_BODY if response else MAX_FRAME), 'response_limit')

    def unique(pairs):
        require(len(pairs) <= 128, 'json_object_limit')
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result

    def integer(value):
        require(len(value) <= 20 and -(2**63) < int(value) < 2**63, 'json_integer_limit')
        return int(value)

    def finite(_):
        raise MetadataAPIError('nonfinite_json')

    def bounded(value, depth=0):
        require(depth <= (16 if response else 18), 'json_depth_limit')
        if type(value) is dict:
            for key, child in value.items():
                require(len(key) <= 512
                        and not any(0xD800 <= ord(char) <= 0xDFFF for char in key),
                        'json_string_limit')
                bounded(child, depth + 1)
        elif type(value) is list:
            require(len(value) <= 1000, 'json_array_limit')
            for child in value:
                bounded(child, depth + 1)
        elif type(value) is str:
            require(len(value) <= MAX_VALUE_STRING
                    and not any(0xD800 <= ord(char) <= 0xDFFF for char in value),
                    'json_string_limit')
        elif type(value) is float:
            require(math.isfinite(value), 'nonfinite_json')

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_int=integer, parse_constant=finite)
        bounded(value)
        require(type(value) in {dict, list}, 'invalid_response_shape')
        return value
    except MetadataAPIError:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise MetadataAPIError('invalid_json') from None


class HeaderReader:
    """Bound initial headers, chunk framing and trailers before stdlib parsing."""

    def __init__(self, stream):
        self.stream = stream
        self.remaining = 16384

    def readline(self, limit=-1):
        line = self.stream.readline(min(4097, self.remaining + 1,
                                        limit if limit >= 0 else 4097))
        self.remaining -= len(line)
        require(self.remaining >= 0 and len(line) <= 4096, 'invalid_headers')
        return line

    def read(self, size=-1):
        return self.stream.read(size)

    def readinto(self, buffer):
        return self.stream.readinto(buffer)

    def flush(self):
        self.stream.flush()

    def close(self):
        self.stream.close()


class BoundedResponse(http.client.HTTPResponse):
    def begin(self):
        if self.headers is None:
            self.fp = HeaderReader(self.fp)
        super().begin()


def response_headers(response, operation, arguments):
    headers = response.getheaders()
    require(len(headers) <= 100 and not response.headers.defects, 'invalid_headers')
    values = {}
    for name, value in headers:
        require(re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name), 'invalid_headers')
        lower = name.lower()
        require(type(value) is str and len(value) <= 4096
                and not any(ord(c) < 32 or ord(c) == 127 for c in value), 'invalid_headers')
        if lower in {'content-length', 'transfer-encoding', 'content-encoding',
                     'content-type', 'link'}:
            require(lower not in values, 'invalid_headers')
            values[lower] = value
    length = values.get('content-length')
    transfer = values.get('transfer-encoding')
    require(transfer in {None, 'chunked'} and not (length is not None and transfer),
            'invalid_headers')
    if length is not None:
        require(re.fullmatch(r'0|[1-9][0-9]{0,7}', length), 'invalid_headers')
        require(int(length) <= MAX_BODY, 'response_limit')
    require(values.get('content-encoding', 'identity') == 'identity', 'invalid_headers')
    media = values.get('content-type', '').split(';')[0].strip().lower()
    require(media in {'application/json', 'application/vnd.github+json'}, 'invalid_headers')
    link = values.get('link')
    link_relations(operation, arguments, link)
    return link, None if length is None else int(length)


def fetch(operation, arguments, token):
    """One concrete verified-TLS GET, without redirect, proxy, fallback or retry."""
    path = route(operation, arguments)
    valid_token(token)
    connection = response = None
    count = 0
    result = {'code': 'worker_failed', 'byte_count': 0}
    try:
        connection = http.client.HTTPSConnection('api.github.com', timeout=10,
                                                 context=ssl.create_default_context())
        connection.response_class = BoundedResponse
        connection.request('GET', path, headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'rc-pretag-metadata-v1',
            'Accept-Encoding': 'identity', 'Connection': 'close',
        })
        response = connection.getresponse()
        status = response.status
        if status != 200:
            code = {401: 'unauthorized', 403: 'forbidden',
                    404: 'not_found_or_not_visible', 429: 'rate_limited'}.get(status)
            if code is None:
                code = ('redirect_rejected' if 300 <= status < 400 else
                        'server_error' if 500 <= status < 600 else 'unexpected_status')
            raise MetadataAPIError(code)
        link, length = response_headers(response, operation, arguments)
        chunks = []
        while True:
            # Unknown-length bodies at the exact cap fail closed without an
            # extra byte read. Declared exact-length bodies close at their end.
            require(count < MAX_BODY or response.isclosed(), 'response_limit')
            chunk = response.read(min(65536, MAX_BODY - count))
            count += len(chunk)
            if not chunk:
                break
            chunks.append(chunk)
        require(length is None or count == length, 'transport_failure')
        value = parse_json(b''.join(chunks))
        expected = list if operation in {'reviews', 'commits'} else dict
        require(type(value) is expected, 'invalid_response_shape')
        result = {'value': value, 'link': link, 'byte_count': count}
    except MetadataAPIError as exc:
        result = {'code': exc.code, 'byte_count': count}
    except http.client.IncompleteRead as exc:
        count += len(exc.partial)
        result = {'code': 'transport_failure', 'byte_count': count}
    except ssl.SSLError:
        result = {'code': 'tls_failure', 'byte_count': count}
    except Exception:
        result = {'code': 'transport_failure', 'byte_count': count}
    finally:
        for resource in (response, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    result = {'code': 'close_failure', 'byte_count': count}
    return result


def read_exact(stream, size):
    pieces = []
    while size:
        piece = stream.read(size)
        require(bool(piece), 'invalid_ipc')
        pieces.append(piece)
        size -= len(piece)
    return b''.join(pieces)


def main():
    """No CLI options; stdin accepts only consecutive typed request frames."""
    sequence = 0
    while True:
        first = sys.stdin.buffer.read(1)
        if not first:
            return
        prefix = first + read_exact(sys.stdin.buffer, 3)
        size = struct.unpack('!I', prefix)[0]
        require(0 < size <= MAX_REQUEST, 'invalid_ipc')
        request = parse_json(read_exact(sys.stdin.buffer, size), response=False)
        require(type(request) is dict and set(request) == {'id', 'operation', 'args', 'token'},
                'invalid_ipc')
        sequence += 1
        require(type(request['id']) is int and request['id'] == sequence <= 128, 'invalid_ipc')
        route(request['operation'], request['args'])
        valid_token(request['token'])
        result = fetch(request['operation'], request['args'], request['token'])
        result.update(id=sequence, operation=request['operation'])
        raw = json.dumps(result, separators=(',', ':'), ensure_ascii=False,
                         allow_nan=False).encode('utf-8')
        require(len(raw) <= MAX_FRAME, 'invalid_ipc')
        sys.stdout.buffer.write(struct.pack('!I', len(raw)) + raw)
        sys.stdout.buffer.flush()
        del request, result, raw


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        sys.exit(1)
