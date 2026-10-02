#!/bin/sh
set -eu
for name in configuration credentials; do
  cp "/run/site/$name.json" "/usr/share/nginx/html/$name.json"
  chown 1000:1000 "/usr/share/nginx/html/$name.json"
  chmod 600 "/usr/share/nginx/html/$name.json"
done
# Container stdio pipes are root-owned; nginx logs to them after dropping privileges.
chown 1000 /proc/self/fd/1 /proc/self/fd/2 2>/dev/null || true
exec setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/clearml "$@"
