#!/bin/sh
set -eu
for name in configuration credentials; do
  [ -s "/run/site/$name.json" ] || { echo "missing /run/site/$name.json; run configure" >&2; exit 1; }
done
# Container stdio pipes are root-owned; nginx logs to them after dropping privileges.
chown 1000 /proc/self/fd/1 /proc/self/fd/2 2>/dev/null || true
exec setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/clearml "$@"
