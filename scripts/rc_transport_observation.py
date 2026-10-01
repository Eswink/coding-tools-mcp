#!/usr/bin/env python3
"""Fixed-target API redirect observation only; never contact storage or read ZIP bytes."""
import http.client
import json
import os
import re
import signal
import sys
from urllib.parse import urlsplit

REPOSITORY = "Eswink/coding-tools-mcp"
REPOSITORY_ID = 1360355522
SOURCE_SHA = "e2e011f7f2a3a1df838bbd588106205b999db610"
RUN_ID = 36796834637
ARTIFACT_ID = 11134440327
SIZE = 912
DIGEST = "sha256:dcc70362712162e99d6884942f0720934bc16c7d6a817361ffbfd1602601fa60"
BASE = "/repos/" + REPOSITORY
RUN = BASE + "/actions/runs/" + str(RUN_ID)
ARTIFACT = BASE + "/actions/artifacts/" + str(ARTIFACT_ID)
PATHS = (BASE, RUN, RUN + "/artifacts?per_page=100&page=1", ARTIFACT, ARTIFACT + "/zip")
MAX_JSON = 131072
MAX_HEADERS = 16384
DEADLINE = 40
SCOPE = "redirect-host-observation-only"


def observation_require(condition):
    if not condition:
        raise ValueError("observation_rejected")


def observation_pairs(pairs):
    result = {}
    for key, value in pairs:
        observation_require(key not in result)
        result[key] = value
    return result


def observation_integer(raw):
    observation_require(len(raw) <= 20)
    value = int(raw)
    observation_require(-(2**63) <= value < 2**63)
    return value


def observation_noninteger(_raw):
    raise ValueError("observation_rejected")


def observation_exact(data, expected):
    observation_require(type(data) is dict)
    for key, value in expected.items():
        observation_require(type(data.get(key)) is type(value) and data[key] == value)


def observation_artifact(data):
    observation_exact(data, {"id": ARTIFACT_ID, "size_in_bytes": SIZE,
                             "digest": DIGEST, "expired": False})
    observation_exact(data.get("workflow_run"), {"id": RUN_ID,
                      "repository_id": REPOSITORY_ID, "head_repository_id": REPOSITORY_ID,
                      "head_sha": SOURCE_SHA})


def observation_hostname(location):
    observation_require(type(location) is str and 1 <= len(location) <= 8192)
    observation_require(all(33 <= ord(c) <= 126 for c in location))
    observation_require(location.startswith("https://") and "#" not in location and "\\" not in location)
    parsed = urlsplit(location)
    host = parsed.hostname or ""
    observation_require(parsed.scheme == "https" and not parsed.username and not parsed.password)
    observation_require(parsed.port in (None, 443) and parsed.netloc.lower() in (host, host + ":443"))
    observation_require(1 <= len(host) <= 253 and "." in host)
    labels = host.split(".")
    observation_require(all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels))
    observation_require(re.fullmatch(r"[a-z]{2,63}", labels[-1]) is not None)
    return host


def observation_get(path, token):
    observation_require(path in PATHS)
    # HTTPSConnection does not implement redirects or consult proxy environment variables.
    connection = http.client.HTTPSConnection("api.github.com", port=443, timeout=10)
    response = None
    try:
        connection.request("GET", path, headers={"Authorization": "Bearer " + token,
                           "Accept": "application/vnd.github+json", "Accept-Encoding": "identity",
                           "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "rc-transport-observation"})
        response = connection.getresponse()
        headers = response.getheaders()
        observation_require(sum(len(k) + len(v) + 4 for k, v in headers) <= MAX_HEADERS)
        lowered = [(key.lower(), value) for key, value in headers]
        locations = [value for key, value in lowered if key == "location"]
        if path == PATHS[-1]:
            observation_require(response.status == 302 and len(locations) == 1)
            return observation_hostname(locations[0])  # Deliberately never read response body.
        observation_require(response.status == 200 and not locations)
        observation_require(not any(key == "link" for key, _ in lowered))
        types = [v for k, v in lowered if k == "content-type"]
        observation_require(len(types) == 1 and types[0].split(";")[0].strip() == "application/json")
        encodings = [v for k, v in lowered if k == "content-encoding"]
        observation_require(not encodings or encodings == ["identity"])
        lengths = [v for k, v in lowered if k == "content-length"]
        observation_require(len(lengths) <= 1)
        if lengths:
            observation_require(re.fullmatch(r"[0-9]{1,6}", lengths[0]) is not None)
            observation_require(int(lengths[0]) <= MAX_JSON and not any(k == "transfer-encoding" for k, _ in lowered))
        raw = response.read(MAX_JSON + 1)
        observation_require(len(raw) <= MAX_JSON and (not lengths or int(lengths[0]) == len(raw)))
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=observation_pairs,
                            parse_int=observation_integer, parse_float=observation_noninteger,
                            parse_constant=observation_noninteger)
        observation_require(type(result) is dict)
        return result
    finally:
        try:
            if response is not None:
                response.close()
        finally:
            connection.close()


def observe_fixed_redirect(token):
    observation_require(type(token) is str and re.fullmatch(r"[A-Za-z0-9_]{1,4096}", token) is not None)
    observation_exact(observation_get(PATHS[0], token), {"id": REPOSITORY_ID, "full_name": REPOSITORY})
    run = observation_get(PATHS[1], token)
    observation_exact(run, {"id": RUN_ID, "head_sha": SOURCE_SHA, "status": "completed", "conclusion": "success"})
    for field in ("repository", "head_repository"):
        observation_exact(run.get(field), {"id": REPOSITORY_ID, "full_name": REPOSITORY})
    listing = observation_get(PATHS[2], token)
    total, items = listing.get("total_count"), listing.get("artifacts")
    observation_require(type(total) is int and 1 <= total <= 100)
    observation_require(type(items) is list and len(items) == total)
    ids = []
    for item in items:
        observation_require(type(item) is dict and type(item.get("id")) is int and item["id"] > 0)
        ids.append(item["id"])
    observation_require(len(set(ids)) == total and ids.count(ARTIFACT_ID) == 1)
    observation_artifact(items[ids.index(ARTIFACT_ID)])
    observation_artifact(observation_get(PATHS[3], token))
    host = observation_get(PATHS[4], token)
    return {"scope": SCOPE, "repository_id": REPOSITORY_ID, "source_sha": SOURCE_SHA,
            "run_id": RUN_ID, "artifact_id": ARTIFACT_ID, "size_in_bytes": SIZE,
            "digest": DIGEST, "expired": False, "http_status": 302, "hostname": host,
            "release_approved": False, "publish_approved": False}


def observation_deadline(_signum, _frame):
    raise TimeoutError("observation_rejected")


def observation_main():
    previous = signal.signal(signal.SIGALRM, observation_deadline)
    signal.setitimer(signal.ITIMER_REAL, DEADLINE)
    try:
        observation_require(len(sys.argv) == 1)
        report = observe_fixed_redirect(os.environ.pop("GH_TOKEN", ""))
    except Exception:
        # No exception text, API data, token, headers or signed URL may escape this boundary.
        print(json.dumps({"scope": SCOPE, "error": "observation_failed",
                          "release_approved": False, "publish_approved": False}, sort_keys=True))
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(observation_main())
