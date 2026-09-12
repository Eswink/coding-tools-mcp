#!/usr/bin/env bash
set -euo pipefail

for command in nginx python3 curl; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'missing required command: %s\n' "$command" >&2
    exit 2
  }
done

root="$(mktemp -d)"
backend_pid=''
nginx_pid=''
cleanup() {
  if [[ -n "$nginx_pid" ]]; then
    kill "$nginx_pid" 2>/dev/null || true
    wait "$nginx_pid" 2>/dev/null || true
  fi
  if [[ -n "$backend_pid" ]]; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
  rm -rf "$root"
}
trap cleanup EXIT

site_root="$root/site"
mkdir -p "$site_root/.well-known/acme-challenge"
printf '%s\n' 'acme-preserved' >"$site_root/.well-known/acme-challenge/fixture"

# Use an exact-path fixture rather than SimpleHTTPRequestHandler. The OAuth
# protected-resource base URI and its /mcp child are both valid application
# routes but cannot both be represented as a regular filesystem path without
# introducing an artificial directory redirect.
cat >"$root/backend.py" <<'PY'
import http.server
import json
import pathlib
import sys

port_file = pathlib.Path(sys.argv[1])
responses = {
    "/mcp": {"backend": "mcp"},
    "/.well-known/oauth-authorization-server": {
        "issuer": "https://fixture.example",
    },
    "/.well-known/oauth-protected-resource": {
        "resource": "https://fixture.example/mcp",
    },
    "/.well-known/oauth-protected-resource/mcp": {
        "resource": "https://fixture.example/mcp",
    },
    "/oauth/authorize": {"backend": "authorize"},
}

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = responses.get(self.path)
        if body is None:
            self.send_error(404)
            return
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        if self.path == "/oauth/token":
            encoded = b'{"backend":"token"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        return

server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port_file.write_text(str(server.server_port), encoding="utf-8")
server.serve_forever()
PY

python3 "$root/backend.py" "$root/backend.port" >"$root/backend.log" 2>&1 &
backend_pid=$!
for _ in $(seq 1 50); do
  [[ -s "$root/backend.port" ]] && break
  kill -0 "$backend_pid" 2>/dev/null || {
    cat "$root/backend.log" >&2
    exit 3
  }
  sleep 0.05
done
[[ -s "$root/backend.port" ]] || {
  printf 'backend did not publish a port\n' >&2
  exit 3
}
backend_port="$(cat "$root/backend.port")"

free_port() {
  python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

write_config() {
  local listen_port="$1"
  local repaired="$2"
  local oauth_locations=''
  if [[ "$repaired" == 'yes' ]]; then
    oauth_locations=$(cat <<EOF
        location = /.well-known/oauth-authorization-server {
            proxy_pass http://127.0.0.1:${backend_port};
        }
        location = /.well-known/oauth-protected-resource {
            proxy_pass http://127.0.0.1:${backend_port};
        }
        location = /.well-known/oauth-protected-resource/mcp {
            proxy_pass http://127.0.0.1:${backend_port};
        }
        location = /oauth/authorize {
            proxy_pass http://127.0.0.1:${backend_port};
        }
        location = /oauth/token {
            proxy_pass http://127.0.0.1:${backend_port};
        }
EOF
)
  fi
  cat >"$root/nginx.conf" <<EOF
worker_processes 1;
pid $root/nginx.pid;
error_log $root/nginx-error.log notice;
events { worker_connections 64; }
http {
    access_log off;
    server {
        listen 127.0.0.1:${listen_port};
        server_name fixture.example;
        root ${site_root};
${oauth_locations}
        location ^~ / {
            proxy_pass http://127.0.0.1:${backend_port};
        }
        # Exact reproduction of the relevant BaoTa-generated prefix.
        # It is longer than '/', so OAuth discovery is served as static content
        # unless exact OAuth locations are added.
        location /.well-known {
            allow all;
        }
    }
}
EOF
}

start_nginx() {
  nginx -t -c "$root/nginx.conf" -p "$root" >/dev/null
  nginx -c "$root/nginx.conf" -p "$root" -g 'daemon off; master_process off;' \
    >"$root/nginx.log" 2>&1 &
  nginx_pid=$!
  for _ in $(seq 1 50); do
    kill -0 "$nginx_pid" 2>/dev/null || {
      cat "$root/nginx.log" >&2
      cat "$root/nginx-error.log" >&2
      exit 4
    }
    if curl --silent --show-error --max-time 1 \
      "http://127.0.0.1:${listen_port}/mcp" >/dev/null 2>&1; then
      return
    fi
    sleep 0.05
  done
  printf 'nginx did not become ready\n' >&2
  exit 4
}

stop_nginx() {
  kill "$nginx_pid" 2>/dev/null || true
  wait "$nginx_pid" 2>/dev/null || true
  nginx_pid=''
}

status_of() {
  curl --silent --show-error --max-time 2 --output /dev/null \
    --write-out '%{http_code}' "$1"
}

assert_status() {
  local expected="$1"
  local url="$2"
  local actual
  actual="$(status_of "$url")"
  if [[ "$actual" != "$expected" ]]; then
    printf 'unexpected status: expected=%s actual=%s url=%s\n' \
      "$expected" "$actual" "$url" >&2
    cat "$root/nginx-error.log" >&2 || true
    exit 5
  fi
}

listen_port="$(free_port)"
write_config "$listen_port" no
start_nginx
assert_status 200 "http://127.0.0.1:${listen_port}/mcp"
assert_status 404 "http://127.0.0.1:${listen_port}/.well-known/oauth-authorization-server"
assert_status 404 "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource"
assert_status 404 "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource/mcp"
assert_status 200 "http://127.0.0.1:${listen_port}/.well-known/acme-challenge/fixture"
printf 'failure-first: plain /.well-known prefix reproduces OAuth discovery 404 while /mcp stays proxied\n'
stop_nginx

listen_port="$(free_port)"
write_config "$listen_port" yes
start_nginx
assert_status 200 "http://127.0.0.1:${listen_port}/mcp"
assert_status 200 "http://127.0.0.1:${listen_port}/.well-known/oauth-authorization-server"
assert_status 200 "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource"
assert_status 200 "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource/mcp"
assert_status 200 "http://127.0.0.1:${listen_port}/.well-known/acme-challenge/fixture"
printf 'candidate: exact OAuth locations override the panel prefix and preserve ACME behavior\n'
