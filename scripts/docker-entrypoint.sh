#!/bin/sh
# Cloud hosts usually mount the data volume owned by root. When the container starts as root, give /data to the
# unprivileged "att" user and run the app as that user. (docker compose starts it as ATT_UID instead: nothing to do.)
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  chown -R att /data
  exec setpriv --reuid=att --regid=att --init-groups "$@"
fi
exec "$@"
