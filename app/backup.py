"""Automatic and on-demand backups of the database.

Uses SQLite's online backup, so a backup is consistent even while teachers are scanning. Each backup is a
complete database file: to restore, stop the server and put the file back as data/attendance.db.
"""
import asyncio
import os
import re
import shutil
import sqlite3
from datetime import datetime, timedelta

from . import config

NAME = re.compile(r"^attendance-\d{8}-\d{6}(-[a-z]+)?\.db$")


def _prune(folder: str) -> None:
    files = sorted(f for f in os.listdir(folder) if NAME.match(f))
    for old in files[:-config.BACKUP_KEEP] if config.BACKUP_KEEP > 0 else []:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass


def backup_now(kind: str = "auto") -> dict:
    """Writes data/backups/attendance-YYYYMMDD-HHMMSS-<kind>.db, copies it to BACKUP_COPY_DIR if set,
    and keeps only the newest BACKUP_KEEP files in each place."""
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    name = f"attendance-{datetime.now():%Y%m%d-%H%M%S}-{kind}.db"
    path = os.path.join(config.BACKUP_DIR, name)
    src, dst = sqlite3.connect(config.DB_PATH), sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    copied, copy_error = False, ""
    if config.BACKUP_COPY_DIR:
        try:
            os.makedirs(config.BACKUP_COPY_DIR, exist_ok=True)
            shutil.copy2(path, os.path.join(config.BACKUP_COPY_DIR, name))
            _prune(config.BACKUP_COPY_DIR)
            copied = True
        except OSError as exc:   # e.g. the USB drive is not plugged in; the main backup still exists
            copy_error = str(exc)
            print(f"[attendance] Backup saved, but copying it to {config.BACKUP_COPY_DIR} failed: {exc}", flush=True)
    _prune(config.BACKUP_DIR)
    return {"name": name, "path": path, "copied": copied, "copy_error": copy_error}


def list_backups() -> list[dict]:
    if not os.path.isdir(config.BACKUP_DIR):
        return []
    out = []
    for f in sorted((f for f in os.listdir(config.BACKUP_DIR) if NAME.match(f)), reverse=True):
        st = os.stat(os.path.join(config.BACKUP_DIR, f))
        out.append({"name": f, "size": st.st_size,
                    "created": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds")})
    return out


def file_path(name: str) -> str | None:
    """Safe lookup for a download: only names made by backup_now(), only inside BACKUP_DIR."""
    p = os.path.join(config.BACKUP_DIR, name)
    return p if NAME.match(name) and os.path.isfile(p) else None


def due() -> bool:
    if config.BACKUP_HOURS <= 0:
        return False
    files = list_backups()
    if not files:
        return True
    newest = datetime.fromisoformat(files[0]["created"])
    return datetime.now().astimezone() - newest >= timedelta(hours=config.BACKUP_HOURS)


async def scheduler() -> None:
    """Runs inside the server: checks every 10 minutes and makes a backup when the newest is old enough."""
    while True:
        try:
            if due():
                r = await asyncio.to_thread(backup_now, "auto")
                print(f"[attendance] Automatic backup: {r['path']}", flush=True)
        except Exception as exc:   # never stop the server because of a backup problem
            print(f"[attendance] Automatic backup failed: {exc}", flush=True)
        await asyncio.sleep(600)
