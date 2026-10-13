import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('admin','teacher','student')),
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- login name: student ID, teacher ID, or 'admin'
  name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '' COLLATE NOCASE,  -- teachers and admin only (for forgot password)
  class_name TEXT NOT NULL DEFAULT '',            -- students only: class ID such as 5S4, from the master list
  position TEXT NOT NULL DEFAULT '',              -- teachers only: position in school, from the master list
  pw_hash TEXT NOT NULL,                          -- '' until the person registers
  approved INTEGER NOT NULL DEFAULT 1,            -- kept from older versions (teacher sign-ups waiting); always 1 now
  active INTEGER NOT NULL DEFAULT 1,              -- 0 = account blocked
  qr_token TEXT UNIQUE,                           -- students only: random value inside the QR
  qr_status TEXT NOT NULL DEFAULT 'active',       -- unregistered | active | terminated (students: must register again)
  qr_printed_at TEXT,                             -- students only: the QR can be printed once
  registered_at TEXT,                             -- students and teachers: when they registered (last time)
  created_at TEXT NOT NULL
);
-- The master list IS the student and teacher rows: the admin's two imports create everyone ('unregistered') with
-- class ID / position and co-curricula. Registering only sets the password (and, for students, the QR).
CREATE TABLE IF NOT EXISTS photos (                -- profile picture, uploaded by the student or teacher
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  mime TEXT NOT NULL,
  data BLOB NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reset_codes (           -- forgot password: one row per user who asked
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  requested_at TEXT NOT NULL,
  code_hash TEXT,                                 -- students: NULL until a teacher or admin issues a code
  expires_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS classes (               -- a co-curriculum (e.g. "Pancaragam Harmonica"), from the master list
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  category TEXT NOT NULL DEFAULT '',              -- uniform | club | sport, or '' (a group teachers could make in older versions)
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS class_teachers (        -- teachers in charge of a class
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (class_id, teacher_id)
);
CREATE TABLE IF NOT EXISTS class_students (
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (class_id, student_id)
);
CREATE TABLE IF NOT EXISTS sessions (              -- one meeting at a venue and time
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  venue TEXT NOT NULL,
  session_date TEXT NOT NULL,                     -- YYYY-MM-DD, local
  start_time TEXT NOT NULL DEFAULT '',            -- HH:MM, local
  end_time TEXT NOT NULL DEFAULT '',
  closed INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_classes (       -- a session can join several classes (A, B, C)
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  PRIMARY KEY (session_id, class_id)
);
CREATE TABLE IF NOT EXISTS attendance (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  checked_in_at TEXT NOT NULL,                    -- UTC
  scanned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  venue TEXT NOT NULL DEFAULT '',                 -- where the scanning teacher was (a split class: Hall A / Hall B)
  UNIQUE (session_id, student_id)                 -- every teacher's scans land in the same list
);
CREATE TABLE IF NOT EXISTS achievements (          -- recorded by a teacher in charge; shown on the student's profile
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  activity TEXT NOT NULL,                         -- e.g. "Basketball", "Pancaragam Harmonica"
  level TEXT NOT NULL,                            -- school | zone | district | state | national | international
  award TEXT NOT NULL,                            -- e.g. "Gold", "Champion", "Participation"
  class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL,   -- the co-curriculum it was recorded for
  added_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  UNIQUE (student_id, year, activity, level, award)
);
CREATE TABLE IF NOT EXISTS audit_log (             -- who changed what (scans are not logged: attendance has scanned_by)
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,                               -- UTC
  actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  actor TEXT NOT NULL,                            -- name and role at that moment, kept even if the account goes
  action TEXT NOT NULL,                           -- e.g. master.edit, qr.terminate, session.delete
  target TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_att_student ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(session_date);
CREATE INDEX IF NOT EXISTS idx_sc_class ON session_classes(class_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    d = os.path.dirname(config.DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone() and \
           "qr_status" not in {r["name"] for r in db.execute("PRAGMA table_info(users)")}:
            raise RuntimeError(f"{config.DB_PATH} was made by an older version of this app. "
                               "Move it away and start again with an empty database.")
        cols = lambda t: {r["name"] for r in db.execute(f"PRAGMA table_info({t})")}  # noqa: E731
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='classes'").fetchone() and "category" not in cols("classes"):
            db.execute("ALTER TABLE classes ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone() and "registered_at" not in cols("users"):
            db.execute("ALTER TABLE users ADD COLUMN registered_at TEXT")
            db.execute("UPDATE users SET registered_at=created_at WHERE role='student'")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone() and "position" not in cols("users"):
            db.execute("ALTER TABLE users ADD COLUMN position TEXT NOT NULL DEFAULT ''")
            # teacher sign-ups that were never approved become teacher master-list entries that still have to register
            db.execute("UPDATE users SET approved=1, qr_status='unregistered', pw_hash='' WHERE role='teacher' AND approved=0")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='achievements'").fetchone() and "class_id" not in cols("achievements"):
            db.execute("ALTER TABLE achievements ADD COLUMN class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL")
            db.execute("ALTER TABLE achievements ADD COLUMN added_by INTEGER REFERENCES users(id) ON DELETE SET NULL")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='attendance'").fetchone() and "venue" not in cols("attendance"):
            db.execute("ALTER TABLE attendance ADD COLUMN venue TEXT NOT NULL DEFAULT ''")
        db.executescript(SCHEMA)
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='master_students'").fetchone():
            # older version kept the master list in its own table: turn every entry into a student row
            for m in db.execute("SELECT * FROM master_students").fetchall():
                if not db.execute("UPDATE users SET name=?, class_name=? WHERE role='student' AND username=?",
                                  (m["name"], m["class_name"], m["student_no"])).rowcount:
                    db.execute("INSERT OR IGNORE INTO users(role,username,name,class_name,pw_hash,qr_status,created_at) "
                               "VALUES ('student',?,?,?,'','unregistered',?)",
                               (m["student_no"], m["name"], m["class_name"], now_iso()))
            db.execute("DROP TABLE master_students")
