"""Private one-download byte worker. No credential discovery or CLI options."""
from __future__ import annotations
from contextlib import closing
import ipaddress
import json
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
REPOSITORY = 'Eswink/coding-tools-mcp'
READ_SIZE = 64 * 1024
READ_TIMEOUT = 15
MAX_ZIP = 2 * 1024**3
MAX_REQUEST = 16384
MAX_FRAME = READ_SIZE + 1
TRUSTED_STORAGE_HOSTS: frozenset[str] = frozenset()
ERROR_CODES = frozenset({
    'invalid_storage_redirect', 'unverified_storage_host',
    'unexpected_artifact_download_status', 'unexpected_storage_status',
    'encoded_storage_response', 'download_size_mismatch',
    'invalid_transport_chunk', 'artifact_transport_failed', 'invalid_transport_ipc',
})


class WireError(ValueError):
    def __init__(self, code):
        self.code = code if code in ERROR_CODES else 'artifact_transport_failed'
        super().__init__(self.code)


def need(ok, code):
    if not ok:
        raise WireError(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def storage_url(value, hosts):
    need(type(value) is str and 0 < len(value) <= 8192, 'invalid_storage_redirect')
    need(not any(ord(c) < 32 or ord(c) == 127 for c in value), 'invalid_storage_redirect')
    failed = False
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname, port = parsed.hostname, parsed.port
    except ValueError:
        failed = True
    need(not failed, 'invalid_storage_redirect')
    need(parsed.scheme == 'https' and parsed.username is None and parsed.password is None
         and port in (None, 443) and not parsed.fragment and bool(parsed.path),
         'invalid_storage_redirect')
    need(type(hostname) is str and len(hostname) <= 253
         and re.fullmatch(r'[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?', hostname) is not None,
         'invalid_storage_redirect')
    need(all(0 < len(label) <= 63 and not label.startswith('-') and not label.endswith('-')
             for label in hostname.split('.')), 'invalid_storage_redirect')
    literal = True
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        literal = False
    need(not literal, 'invalid_storage_redirect')
    need(hostname in hosts, 'unverified_storage_host')
    return value


def download(request, emit, opener=None):
    """Preserve existing HTTP rejection rules; all blocking I/O lives here."""
    size, token, ident = (request[k] for k in ('size', 'token', 'id'))
    opener = opener or urllib.request.build_opener(NoRedirect())
    api_request = urllib.request.Request(
        f'{API}/repos/{REPOSITORY}/actions/artifacts/{ident}/zip',
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'}, method='GET')
    try:
        redirect = opener.open(api_request, timeout=READ_TIMEOUT)
    except urllib.error.HTTPError as error:
        redirect = error
    with closing(redirect):
        need(redirect.code == 302, 'unexpected_artifact_download_status')
        locations = redirect.headers.get_all('Location', [])
        need(len(locations) == 1, 'invalid_storage_redirect')
        location = storage_url(locations[0], TRUSTED_STORAGE_HOSTS)
    storage_request = urllib.request.Request(location,
        headers={'Accept': 'application/zip'}, method='GET')
    with closing(opener.open(storage_request, timeout=READ_TIMEOUT)) as response:
        need(response.code == 200, 'unexpected_storage_status')
        encodings = response.headers.get_all('Content-Encoding', [])
        need(not encodings or encodings == ['identity'], 'encoded_storage_response')
        lengths = response.headers.get_all('Content-Length', [])
        need(not lengths or (len(lengths) == 1 and re.fullmatch(r'[1-9][0-9]*', lengths[0])
                            and int(lengths[0]) == size), 'download_size_mismatch')
        total = 0
        while True:
            block = response.read1(min(READ_SIZE, size - total + 1))
            need(type(block) is bytes, 'invalid_transport_chunk')
            if not block:
                break
            total += len(block)
            need(total <= size and total <= MAX_ZIP, 'download_size_mismatch')
            emit(b'B' + block)
    # Both closing contexts completed before DONE. Count/hash authority is parent-owned.
    emit(b'D')


def read_exact(stream, size):
    result = bytearray()
    while len(result) < size:
        block = stream.read(size - len(result))
        need(bool(block), 'invalid_transport_ipc')
        result.extend(block)
    return bytes(result)


def emit(frame):
    need(0 < len(frame) <= MAX_FRAME, 'invalid_transport_ipc')
    sys.stdout.buffer.write(struct.pack('!I', len(frame)) + frame)
    sys.stdout.buffer.flush()


def main(opener=None):
    emit(b'R')
    size = struct.unpack('!I', read_exact(sys.stdin.buffer, 4))[0]
    need(0 < size <= MAX_REQUEST, 'invalid_transport_ipc')
    request = json.loads(read_exact(sys.stdin.buffer, size))
    need(type(request) is dict and set(request) == {'id', 'size', 'token'}, 'invalid_transport_ipc')
    need(type(request['id']) is int and request['id'] > 0
         and type(request['size']) is int and 0 < request['size'] <= MAX_ZIP
         and type(request['token']) is str and bool(request['token']), 'invalid_transport_ipc')
    code = None
    try:
        download(request, emit, opener)
    except WireError as error:
        code = error.code
    except BaseException:
        code = 'artifact_transport_failed'
    # Emit only sanitized scalars outside the exception scope, never raw objects.
    if code is not None:
        emit(b'E' + code.encode('ascii'))
        return 1
    return 0


if __name__ == '__main__':
    result = 1
    try:
        result = main()
    except BaseException:
        pass
    sys.exit(result)
