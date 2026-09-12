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

backend_root="$root/backend"
site_root="$root/site"
mkdir -p "$backend_root/.well-known/oauth-protected-resource" \
  "$site_root/.well-known/acme-challenge"
printf '%s\n' '{"backend":"mcp"}' >"$backend_root/mcp"
printf '%s\n' '{"issuer":"https://fixture.example"}' \
  >"$backend_root/.well-known/oauth-authorization-server"
printf '%s\n' '{"resource":"https://fixture.example/mcp"}' \
  >"$backend_root/.well-known/oauth-protected-resource/index.html"
printf '%s\n' '{"resource":"https://fixture.example/mcp"}' \
  >"$backend_root/.well-known/oauth-protected-resource/mcp"
printf '%s\n' 'acme-preserved' >"$site_root/.well-known/acme-challenge/fixture"

cat >"$root/backend.py" <<'PY'
import functools
import http.server
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
port_file = pathlib.Path(sys.argv[2])
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
port_file.write_text(str(server.server_port), encoding="utf-8")
server.serve_forever()
PY

python3 "$root/backend.py" "$backend_root" "$root/backend.port" \
  >"$root/backend.log" 2>&1 &
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

listen_port="$(free_port)"
write_config "$listen_port" no
start_nginx
[[ "$(status_of "http://127.0.0.1:${listen_port}/mcp")" == '200' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/oauth-authorization-server")" == '404' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource")" == '404' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource/mcp")" == '404' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/acme-challenge/fixture")" == '200' ]]
printf 'failure-first: plain /.well-known prefix reproduces OAuth discovery 404 while /mcp stays proxied\n'
stop_nginx

listen_port="$(free_port)"
write_config "$listen_port" yes
start_nginx
[[ "$(status_of "http://127.0.0.1:${listen_port}/mcp")" == '200' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/oauth-authorization-server")" == '200' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource")" == '200' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/oauth-protected-resource/mcp")" == '200' ]]
[[ "$(status_of "http://127.0.0.1:${listen_port}/.well-known/acme-challenge/fixture")" == '200' ]]
printf 'candidate: exact OAuth locations override the panel prefix and preserve ACME behavior\n'
