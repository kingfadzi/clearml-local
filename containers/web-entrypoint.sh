#!/bin/sh
set -eu
cp /run/site-configuration.json /usr/share/nginx/html/configuration.json
chown 1000:1000 /usr/share/nginx/html/configuration.json
chmod 600 /usr/share/nginx/html/configuration.json
exec setpriv --reuid=1000 --regid=1000 --init-groups "$@"
