"""All settings come from environment variables (see .env.example)."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


DB_PATH = os.getenv("ATT_DB_PATH", "data/attendance.db")
LOGIN_HOURS = _int("ATT_LOGIN_HOURS", 12)
RESET_MINUTES = _int("ATT_RESET_MINUTES", 30)        # how long a forgot-password code works

# First start only: the admin account is created with this password (ATT_ADMIN_TOKEN is the old name).
# If neither is set, a random one is printed in the console.
ADMIN_PASSWORD = os.getenv("ATT_ADMIN_PASSWORD") or os.getenv("ATT_ADMIN_TOKEN", "")
ADMIN_EMAIL = os.getenv("ATT_ADMIN_EMAIL", "")

# Email for teachers' and the admin's forgot-password codes. Without SMTP_HOST the code is printed in the
# server console instead. Students have no email: a teacher or the admin gives them a code.
SMTP_HOST = os.getenv("ATT_SMTP_HOST", "")
SMTP_PORT = _int("ATT_SMTP_PORT", 587)
SMTP_USER = os.getenv("ATT_SMTP_USER", "")
SMTP_PASSWORD = os.getenv("ATT_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("ATT_SMTP_FROM", "") or SMTP_USER
SMTP_SSL = os.getenv("ATT_SMTP_SSL", "false").lower() == "true"   # true for port 465, false for STARTTLS on 587

# Automatic backups: a copy of the database every BACKUP_HOURS (0 = off), keeping the newest BACKUP_KEEP.
# BACKUP_COPY_DIR is an optional second place (a USB drive, a OneDrive or Google Drive folder) so one broken
# disk cannot lose everything.
BACKUP_DIR = os.getenv("ATT_BACKUP_DIR") or os.path.join(os.path.dirname(DB_PATH) or ".", "backups")
BACKUP_HOURS = _int("ATT_BACKUP_HOURS", 24)
BACKUP_KEEP = _int("ATT_BACKUP_KEEP", 30)
BACKUP_COPY_DIR = os.getenv("ATT_BACKUP_COPY_DIR", "")