"""Helpers shared by the admin, teacher and student routes: the master list (students and teachers)."""
import re
import unicodedata

from fastapi import HTTPException

from .db import now_iso

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
ID = r"[A-Za-z0-9._/-]+"


def email_taken(db, email: str, except_id: int = 0) -> bool:
    return bool(email) and db.execute("SELECT 1 FROM users WHERE email=? AND id<>?", (email, except_id)).fetchone() is not None


def norm(value: str) -> str:
    """'AINA  binti ali' == 'Aina Binti Ali'"""
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


# The three co-curricula every student has, as in the school's records.
COCU = {"uniform": "Uniform body", "club": "Club / society", "sport": "Sport / game"}


def set_cocu(db, student_id: int, category: str, activity: str) -> None:
    """Puts the student in exactly one co-curriculum of this category (or none if activity is empty).
    The co-curriculum is created the first time it appears; the admin then adds its teachers in charge."""
    db.execute("DELETE FROM class_students WHERE student_id=? AND class_id IN (SELECT id FROM classes WHERE category=?)",
               (student_id, category))
    activity = " ".join(activity.split())
    if not activity:
        return
    c = db.execute("SELECT id, category FROM classes WHERE name=?", (activity,)).fetchone()
    if c and c["category"] not in ("", category):
        raise HTTPException(409, f"'{activity}' is already a {COCU[c['category']].lower()}, not a {COCU[category].lower()}")
    if c:
        cid = c["id"]
        if not c["category"]:   # a group a teacher made with this exact name becomes the co-curriculum
            db.execute("UPDATE classes SET category=? WHERE id=?", (category, cid))
    else:
        cid = db.execute("INSERT INTO classes(name, category, created_at) VALUES (?,?,?)",
                         (activity, category, now_iso())).lastrowid
    db.execute("INSERT OR IGNORE INTO class_students(class_id, student_id) VALUES (?,?)", (cid, student_id))


def cocu_of(db, student_id: int) -> dict:
    """{'uniform': 'Gadet Police', 'club': 'Pancaragam Harmonica', 'sport': 'Basketball'} ('' if none)."""
    out = dict.fromkeys(COCU, "")
    for r in db.execute("SELECT c.category, c.name FROM class_students m JOIN classes c ON c.id=m.class_id "
                        "WHERE m.student_id=? AND c.category<>''", (student_id,)):
        out[r["category"]] = r["name"]
    return out


def upsert_student(db, student_no: str, name: str, class_name: str, cocu: dict | None = None) -> bool:
    """Adds or updates one student of the master list. cocu: {category: activity} for the columns given
    (a category left out is not touched; an empty value removes it). Returns True when the student is new."""
    student_no, name, class_name = student_no.strip(), " ".join(name.split()), class_name.strip().upper()
    row = db.execute("SELECT id, role FROM users WHERE username=?", (student_no,)).fetchone()
    if row and row["role"] != "student":
        raise HTTPException(409, f"{student_no} is already used as a {row['role']} username")
    if row:
        sid = row["id"]
        db.execute("UPDATE users SET name=?, class_name=? WHERE id=?", (name, class_name, sid))
    else:
        sid = db.execute("INSERT INTO users(role,username,name,class_name,pw_hash,qr_status,created_at) "
                         "VALUES ('student',?,?,?,'','unregistered',?)",
                         (student_no, name, class_name, now_iso())).lastrowid
    for category, activity in (cocu or {}).items():
        set_cocu(db, sid, category, activity or "")
    return row is None


def check_id(value: str, what: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{what} is empty")
    if len(value) > 40 or not re.fullmatch(ID, value):
        raise ValueError(f"{what} '{value[:40]}' can only use letters, numbers and . _ / -")
    return value


def upsert_teacher(db, teacher_no: str, name: str, position: str, email: str = "", cocu: list[str] | None = None) -> bool:
    """Adds or updates one teacher of the master list. cocu: the co-curricula they are in charge of (replaces the
    old list; None = leave as it is). Every name must already be a co-curriculum from the student master list,
    so a teacher can never be put in charge of something that does not exist. Returns True when the teacher is new."""
    teacher_no, name, position, email = teacher_no.strip(), " ".join(name.split()), " ".join(position.split()), email.strip()
    row = db.execute("SELECT id, role FROM users WHERE username=?", (teacher_no,)).fetchone()
    if row and row["role"] != "teacher":
        raise ValueError(f"{teacher_no} is already used as a {row['role']} ID")
    if email and not re.fullmatch(EMAIL, email):
        raise ValueError(f"email '{email[:60]}' does not look right")
    ids = []
    for activity in cocu or []:
        c = db.execute("SELECT id FROM classes WHERE name=? AND category<>''", (activity,)).fetchone()
        if not c:
            raise ValueError(f"'{activity}' is not a co-curriculum on the student master list (import the students first, "
                             "and check the spelling)")
        ids.append(c["id"])
    if row:
        tid = row["id"]
        db.execute("UPDATE users SET name=?, position=? WHERE id=?", (name, position, tid))
    else:
        tid = db.execute("INSERT INTO users(role,username,name,position,pw_hash,qr_status,created_at) "
                         "VALUES ('teacher',?,?,?,'','unregistered',?)", (teacher_no, name, position, now_iso())).lastrowid
    if email and not email_taken(db, email, tid):
        db.execute("UPDATE users SET email=? WHERE id=? AND (email='' OR qr_status='unregistered')", (email, tid))
    if cocu is not None:
        db.execute("DELETE FROM class_teachers WHERE teacher_id=?", (tid,))
        db.executemany("INSERT OR IGNORE INTO class_teachers(class_id, teacher_id) VALUES (?,?)", [(c, tid) for c in ids])
    return row is None


# Achievement levels, lowest first. Malay names in the school's records are accepted too.
LEVELS = {"school": "School", "sekolah": "School", "zone": "Zone", "zon": "Zone", "district": "District",
          "daerah": "District", "state": "State", "negeri": "State", "national": "National", "kebangsaan": "National",
          "international": "International", "antarabangsa": "International"}


def student_row(db, sid: int):
    s = db.execute("SELECT * FROM users WHERE id=? AND role='student'", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Student not found")
    return s
