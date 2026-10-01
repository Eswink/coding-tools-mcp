#!/usr/bin/env python3
"""One fixed authenticated artifact byte proof; no artifact parser or file output."""
import hashlib
import http.client
import json
import os
import signal
import sys
import time
from urllib.parse import urlsplit
import rc_transport_observation as observation

HOST = "productionresultssa5.blob.core.windows.net"
SCOPE = "fixed-artifact-byte-transport-proof-only"
STATE = [0, None]
END = 0.0
CODES = frozenset(range(1, 33)) | frozenset(range(40, 54))


def proof_require(condition, code):
    if not condition:
        raise observation.ObservationRejected(code)


def proof_time():
    proof_require(time.monotonic() < END, 40)


def proof_stage(stage):
    STATE[:] = [stage, None]
    proof_time()


def proof_api(path, token):
    proof_time()
    result = observation.observation_get(path, token)
    proof_time()
    return result


def proof_metadata(token):
    observation.observation_exact(proof_api(observation.PATHS[0], token),
                                 {"id": observation.REPOSITORY_ID, "full_name": observation.REPOSITORY})
    run = proof_api(observation.PATHS[1], token)
    observation.observation_exact(run, {"id": observation.RUN_ID, "head_sha": observation.SOURCE_SHA,
                                      "status": "completed", "conclusion": "success"})
    for field in ("repository", "head_repository"):
        observation.observation_exact(run.get(field), {"id": observation.REPOSITORY_ID, "full_name": observation.REPOSITORY})
    listing = proof_api(observation.PATHS[2], token)
    total, items = listing.get("total_count"), listing.get("artifacts")
    proof_require(type(total) is int and 1 <= total <= 100, 27)
    proof_require(type(items) is list and len(items) == total, 28)
    ids = []
    for item in items:
        proof_require(type(item) is dict and type(item.get("id")) is int and item["id"] > 0, 29)
        ids.append(item["id"])
    proof_require(len(set(ids)) == total and ids.count(observation.ARTIFACT_ID) == 1, 30)
    observation.observation_artifact(items[ids.index(observation.ARTIFACT_ID)])
    observation.observation_artifact(proof_api(observation.PATHS[3], token))
    return (observation.REPOSITORY_ID, observation.SOURCE_SHA, observation.RUN_ID,
            observation.ARTIFACT_ID, observation.SIZE, observation.DIGEST, False, tuple(sorted(ids)))


def proof_headers(response):
    if type(response.status) is int and 100 <= response.status <= 599:
        STATE[1] = response.status
    headers = response.getheaders()
    proof_require(sum(len(k) + len(v) + 4 for k, v in headers) <= observation.MAX_HEADERS, 41)
    return [(k.lower(), v) for k, v in headers]


def proof_redirect(token):
    proof_time()
    urlsplit.cache_clear()
    connection = http.client.HTTPSConnection("api.github.com", port=443, timeout=10)
    response = None
    try:
        connection.request("GET", observation.PATHS[4], headers={"Authorization": "Bearer " + token,
                           "Accept": "application/vnd.github+json", "Accept-Encoding": "identity",
                           "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "rc-byte-proof"})
        response = connection.getresponse()
        headers = proof_headers(response)
        locations = [v for k, v in headers if k == "location"]
        proof_require(response.status == 302 and len(locations) == 1, 42)
        location = locations[0]
        proof_require(observation.observation_hostname(location) == HOST, 43)
        parsed = urlsplit(location)
        path = parsed.path or "/"
        proof_require(path.startswith("/") and not path.startswith("//"), 44)
        proof_time()
        return path + ("?" + parsed.query if "?" in location else "")
    finally:
        try:
            urlsplit.cache_clear()
        finally:
            try:
                if response is not None:
                    response.close()
            finally:
                connection.close()


def proof_storage(target):
    proof_time()
    proof_require(type(target) is str and 1 <= len(target) <= 8192 and target.startswith("/")
                  and not target.startswith("//") and all(33 <= ord(c) <= 126 for c in target)
                  and "#" not in target and "\\" not in target, 44)
    connection = http.client.HTTPSConnection(HOST, port=443, timeout=10)
    response = None
    try:
        connection.request("GET", target, headers={"Accept-Encoding": "identity", "Connection": "close"})
        response = connection.getresponse()
        headers = proof_headers(response)
        proof_require(response.status == 200, 45)
        proof_require(not any(k in ("location", "transfer-encoding", "content-range") for k, _ in headers), 46)
        proof_require([v for k, v in headers if k == "content-length"] == [str(observation.SIZE)], 47)
        encoding = [v for k, v in headers if k == "content-encoding"]
        proof_require(not encoding or encoding == ["identity"], 48)
        payload = response.read(observation.SIZE + 1)
        proof_require(type(payload) is bytes and len(payload) == observation.SIZE, 49)
        proof_time()
        return payload
    finally:
        try:
            if response is not None:
                response.close()
        finally:
            connection.close()


def proof_run(token):
    proof_stage(1)
    proof_require(type(token) is str and 1 <= len(token) <= 4096
                  and observation.re.fullmatch(r"[A-Za-z0-9._~+/\-]+=*", token) is not None, 26)
    proof_stage(2)
    before = proof_metadata(token)
    proof_stage(3)
    target = proof_redirect(token)
    proof_stage(4)
    payload = proof_storage(target)
    target = None
    proof_stage(5)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    payload = None
    proof_require(digest == before[5] == observation.DIGEST, 50)
    proof_stage(6)
    proof_require(proof_metadata(token) == before, 51)
    proof_time()
    return {"scope": SCOPE, "repository_id": observation.REPOSITORY_ID, "source_sha": observation.SOURCE_SHA,
            "run_id": observation.RUN_ID, "artifact_id": observation.ARTIFACT_ID, "hostname": HOST,
            "redirect_http_status": 302, "storage_http_status": 200, "size_in_bytes": observation.SIZE,
            "digest": digest, "byte_proof_verified": True, "metadata_rechecked": True,
            "snapshot_atomic": False, "release_approved": False, "publish_approved": False}


def proof_main():
    global END
    STATE[:] = [0, None]
    previous = None
    try:
        END = time.monotonic() + 40
        try:
            token = os.environ.pop("GH_TOKEN", "")
            previous = signal.signal(signal.SIGALRM, observation.observation_deadline)
            signal.setitimer(signal.ITIMER_REAL, 40)
            proof_require(len(sys.argv) == 1, 31)
            proof_require(sys.implementation.name == "cpython" and sys.version_info[:3] == (3, 12, 14), 52)
            report = proof_run(token)
        finally:
            try:
                urlsplit.cache_clear()
            finally:
                try:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                finally:
                    if previous is not None:
                        signal.signal(signal.SIGALRM, previous)
        proof_time()
    except (Exception, KeyboardInterrupt) as error:
        code = getattr(error, "predicate_id", 0) if type(error) is observation.ObservationRejected else 0
        stage, status = STATE if type(STATE) is list and len(STATE) == 2 else (0, None)
        stage = stage if type(stage) is int and 0 <= stage <= 6 else 0
        if stage in (2, 6) and type(observation.OBSERVATION_STATE) is list and len(observation.OBSERVATION_STATE) == 2:
            status = observation.OBSERVATION_STATE[1]
        failure = {"scope": SCOPE, "error": "byte_transport_failed", "stage_id": stage,
                   "predicate_id": code if type(code) is int and code in CODES else 0,
                   "release_approved": False, "publish_approved": False}
        if type(status) is int and 100 <= status <= 599:
            failure["http_status"] = status
        print(json.dumps(failure, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(proof_main())
