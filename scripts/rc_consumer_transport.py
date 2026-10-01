"""Read-only authenticated bytes transport; no storage URL or token is retained."""
from __future__ import annotations

from contextlib import closing
import hashlib
import ipaddress
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from rc_consumer_io import ConsumerError, need

REPOSITORY = 'Eswink/coding-tools-mcp'
API = 'https://api.github.com'
MAX_ZIP = 2 * 1024**3
READ_SIZE = 64 * 1024
READ_TIMEOUT = 15
TOTAL_TIMEOUT = 300
# Deliberately empty until an exact-artifact hosted no-follow observation and
# separately reviewed byte proof establish the storage transport contract.
TRUSTED_STORAGE_HOSTS: frozenset[str] = frozenset()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def storage_url(value: str) -> str:
    need(type(value) is str and 0 < len(value) <= 8192, 'invalid_storage_redirect')
    need(not any(ord(c) < 32 or ord(c) == 127 for c in value), 'invalid_storage_redirect')
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname, port = parsed.hostname, parsed.port
    except ValueError:
        raise ConsumerError('invalid_storage_redirect') from None
    need(parsed.scheme == 'https' and parsed.username is None and parsed.password is None
         and port in (None, 443) and not parsed.fragment and bool(parsed.path),
         'invalid_storage_redirect')
    need(type(hostname) is str and len(hostname) <= 253
         and re.fullmatch(r'[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?', hostname) is not None,
         'invalid_storage_redirect')
    need(all(0 < len(label) <= 63 and not label.startswith('-') and not label.endswith('-')
             for label in hostname.split('.')), 'invalid_storage_redirect')
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ConsumerError('invalid_storage_redirect')
    need(hostname in TRUSTED_STORAGE_HOSTS, 'unverified_storage_host')
    return value


def remaining(deadline: float, clock) -> float:
    value = deadline - clock()
    need(value > 0, 'transport_deadline_exceeded')
    return min(READ_TIMEOUT, value)


def download_artifact_zip(api, artifact: dict, destination, *, opener=None, clock=time.monotonic):
    """Authenticate exact size/hash before returning bytes to any archive parser.

    Injectable transport/clock are library test seams; the CLI exposes neither.
    API metadata is mandatory and is supplied by the authenticated snapshot.
    """
    ident, size, digest = (artifact.get(k) for k in ('id', 'size_in_bytes', 'digest'))
    need(type(ident) is int and ident > 0 and type(size) is int and 0 < size <= MAX_ZIP,
         'invalid_download_metadata')
    need(type(digest) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None,
         'invalid_download_metadata')
    need(type(api.token) is str and bool(api.token), 'missing_actions_read_token')
    need(bool(TRUSTED_STORAGE_HOSTS), 'storage_transport_unverified')
    opener = opener or urllib.request.build_opener(NoRedirect())
    deadline = clock() + TOTAL_TIMEOUT
    request = urllib.request.Request(f'{API}/repos/{REPOSITORY}/actions/artifacts/{ident}/zip',
        headers={'Authorization': 'Bearer ' + api.token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'}, method='GET')
    try:
        try:
            redirect = opener.open(request, timeout=remaining(deadline, clock))
        except urllib.error.HTTPError as error:
            redirect = error
        with closing(redirect):
            need(redirect.code == 302, 'unexpected_artifact_download_status')
            locations = redirect.headers.get_all('Location', [])
            need(len(locations) == 1, 'invalid_storage_redirect')
            location = storage_url(locations[0])
        # A new Request has no Authorization, cookies, API headers or Referer.
        storage_request = urllib.request.Request(location,
            headers={'Accept': 'application/zip'}, method='GET')
        with closing(opener.open(storage_request, timeout=remaining(deadline, clock))) as response:
            need(response.code == 200, 'unexpected_storage_status')
            encodings = response.headers.get_all('Content-Encoding', [])
            need(not encodings or encodings == ['identity'], 'encoded_storage_response')
            lengths = response.headers.get_all('Content-Length', [])
            need(not lengths or (len(lengths) == 1 and re.fullmatch(r'[1-9][0-9]*', lengths[0])
                                and int(lengths[0]) == size), 'download_size_mismatch')
            total, hasher = 0, hashlib.sha256()
            with destination.open('artifact.zip', 'xb') as output:
                while True:
                    remaining(deadline, clock)
                    try:
                        block = response.read1(min(READ_SIZE, size - total + 1))
                    except Exception:
                        raise ConsumerError('artifact_transport_failed') from None
                    remaining(deadline, clock)
                    need(type(block) is bytes, 'invalid_transport_chunk')
                    if not block:
                        break
                    total += len(block)
                    need(total <= size and total <= MAX_ZIP, 'download_size_mismatch')
                    hasher.update(block)
                    output.write(block)
                need(total == size, 'download_size_mismatch')
                need('sha256:' + hasher.hexdigest() == digest, 'download_digest_mismatch')
                output.flush()
                __import__('os').fsync(output.fileno())
        return destination.path / 'artifact.zip'
    except ConsumerError:
        raise
    except Exception:
        # HTTPError and URLError reprs may contain signed URLs or response bodies.
        raise ConsumerError('artifact_transport_failed') from None
