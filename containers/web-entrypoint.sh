#!/bin/sh
set -eu
cp /run/site-configuration.json /usr/share/nginx/html/configuration.json
chown 1000:1000 /usr/share/nginx/html/configuration.json
chmod 600 /usr/share/nginx/html/configuration.json
# Container stdio pipes are root-owned; nginx logs to them after dropping privileges.
chown 1000 /proc/self/fd/1 /proc/self/fd/2 2>/dev/null || true
exec setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/clearml "$@"
