#!/usr/bin/env sh
# Manual backup. Run from the project folder.
set -e
docker compose exec -T app python -c "import sqlite3,datetime,os;os.makedirs('/data/backups',exist_ok=True);d='/data/backups/attendance-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.db';s=sqlite3.connect('/data/attendance.db');t=sqlite3.connect(d);s.backup(t);t.close();print(d)"
echo "Backups are in ./data/backups. Copy that folder to a USB drive or cloud storage."
