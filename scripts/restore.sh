#!/usr/bin/env sh
# Usage: scripts/restore.sh data/backups/attendance-YYYYMMDD-HHMMSS.db
set -e
[ -f "$1" ] || { echo "Give a backup file path"; exit 1; }
docker compose stop app
cp data/attendance.db "data/attendance.before-restore.db" 2>/dev/null || true
rm -f data/attendance.db-wal data/attendance.db-shm
cp "$1" data/attendance.db
docker compose start app
echo "Restored from $1"
