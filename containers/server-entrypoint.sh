#!/bin/bash
set -euo pipefail
if [ "$(id -u)" = 0 ]; then
  mkdir -p /opt/clearml/config /mnt/fileserver /var/log/clearml
  cp -a /run/clearml-config/. /opt/clearml/config/
  chown -R 1000:1000 /opt/clearml/config
  chown 1000:1000 /mnt/fileserver /var/log/clearml
  exec setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/clearml "$0" "$@"
fi
case "${1:-}" in
  apiserver)
    python -m apiserver.apierrors_generator
    exec gunicorn --workers "${API_WORKERS:-4}" --timeout 600 --bind 0.0.0.0:8008 apiserver.server:app ;;
  fileserver)
    cd /opt/clearml/fileserver
    exec gunicorn --timeout 600 --bind 0.0.0.0:8081 fileserver:app ;;
  async_delete)
    export PYTHONPATH=/opt/clearml/apiserver
    exec python -m jobs.async_urls_delete --fileserver-host http://fileserver:8081 ;;
  check-databases) exec python /opt/clearml/check-databases.py ;;
  *) exec "$@" ;;
esac
