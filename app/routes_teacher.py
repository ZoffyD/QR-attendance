"""Teachers. Everything is limited to the co-curricula a teacher is in charge of, as set by the admin's
teacher master list, so a teacher cannot pick, see or record anyone else's.

- A co-curriculum's members come only from the student master list; nobody adds students by hand.
- A session is one meeting at a venue and time, for one or more of the teacher's own co-curricula.
- Every teacher in charge of a co-curriculum in a session can scan into the same attendance list.
- Scanning a student who is not a member is refused and records nothing; a wrong check-in can be undone
  within UNDO_MINUTES. Every check-in and undo is in the activity log.
"""
import csv
import io
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .accounts import LEVELS, student_row
from .audit import audit
from .db import get_db, now_iso
from .security import User, issue_reset_code, staff, teacher_only
from .util import token_from_code

router = APIRouter(prefix="/api")
TIME = r"^(\d{2}:\d{2})?$"
UNDO_MINUTES = 10


# ------------------------------------------------------------------ access rules
def own_class(db, u: User, cid: int):
    c = db.execute("SELECT * FROM classes WHERE id=?", (cid,)).fetchone()
    if not c or (u.role == "teacher" and not db.execute(
            "SELECT 1 FROM class_teachers WHERE class_id=? AND teacher_id=?", (cid, u.id)).fetchone()):
        raise HTTPException(404, "Co-curriculum not found, or you are not in charge of it")
    return c


def own_session(db, u: User, sid: int):
    s = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not s or (u.role == "teacher" and not db.execute(
            "SELECT 1 FROM session_classes sc JOIN class_teachers ct ON ct.class_id=sc.class_id "
            "WHERE sc.session_id=? AND ct.teacher_id=?", (sid, u.id)).fetchone()):
        raise HTTPException(404, "Session not found, or you are not in charge of it")
    return s


def own_student(db, u: User, sid: int):
    """A teacher can only act on students who are members of one of their co-curricula."""
    s = student_row(db, sid)
    if not db.execute("SELECT 1 FROM class_students m JOIN class_teachers ct ON ct.class_id=m.class_id "
                      "WHERE m.student_id=? AND ct.teacher_id=?", (sid, u.id)).fetchone():
        raise HTTPException(404, "This student is not in any co-curriculum you are in charge of")
    return s


def who(s) -> str:
    """'Aina Ali (S001)' for the activity log."""
    return f"{s['name']} ({s['username']})"


def session_label(db, sid: int) -> str:
    """'Weekly practice · 2026-10-13 14:00–16:00 · Dewan · Basketball' for the activity log."""
    s = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    t = s["start_time"] + (f"–{s['end_time']}" if s["end_time"] else "")
    return " · ".join(x for x in (s["title"], f"{s['session_date']} {t}".strip(), s["venue"],
                                  ", ".join(c["name"] for c in session_classes(db, sid))) if x)


def session_classes(db, sid: int) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT c.id, c.name FROM session_classes sc JOIN classes c ON c.id=sc.class_id "
                                        "WHERE sc.session_id=? ORDER BY c.name", (sid,))]


def has_photo(db, uid: int) -> bool:
    return db.execute("SELECT 1 FROM photos WHERE user_id=?", (uid,)).fetchone() is not None


# ------------------------------------------------------------------ the teacher's own profile
@router.get("/teacher/me")
def profile(u: User = Depends(teacher_only)):
    with get_db() as db:
        t = db.execute("SELECT * FROM users WHERE id=?", (u.id,)).fetchone()
        classes = [dict(r) for r in db.execute(
            "SELECT c.id, c.name, c.category, "
            "(SELECT group_concat(t2.name, ', ') FROM class_teachers x JOIN users t2 ON t2.id=x.teacher_id "
            " WHERE x.class_id=c.id AND x.teacher_id<>?) AS co_teachers, "
            "(SELECT COUNT(*) FROM class_students m WHERE m.class_id=c.id) AS students, "
            "(SELECT COUNT(*) FROM class_students m JOIN users s ON s.id=m.student_id "
            " WHERE m.class_id=c.id AND s.qr_status<>'unregistered') AS registered, "
            "(SELECT COUNT(*) FROM session_classes sc WHERE sc.class_id=c.id) AS sessions "
            "FROM class_teachers ct JOIN classes c ON c.id=ct.class_id WHERE ct.teacher_id=? "
            "ORDER BY c.category='', c.category, c.name", (u.id, u.id))]
        return {"id": t["id"], "teacher_no": t["username"], "name": t["name"], "position": t["position"],
                "email": t["email"], "registered_at": t["registered_at"], "has_photo": has_photo(db, u.id),
                "cocurricula": classes}


# ------------------------------------------------------------------ my students
@router.get("/students")
def list_students(u: User = Depends(teacher_only)):
    """The students of the co-curricula this teacher is in charge of (and nobody else)."""
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT s.id, s.username AS student_no, s.name, s.class_name, s.qr_status, s.qr_printed_at, s.active, "
            "(SELECT group_concat(c.name, ', ') FROM class_students m JOIN classes c ON c.id=m.class_id "
            " JOIN class_teachers ct ON ct.class_id=c.id AND ct.teacher_id=? WHERE m.student_id=s.id) AS classes, "
            "(SELECT COUNT(*) FROM attendance a WHERE a.student_id=s.id) AS attended, "
            "EXISTS(SELECT 1 FROM photos p WHERE p.user_id=s.id) AS has_photo, "
            "(SELECT r.requested_at FROM reset_codes r WHERE r.user_id=s.id AND r.code_hash IS NULL) AS reset_requested "
            "FROM users s WHERE s.role='student' AND EXISTS(SELECT 1 FROM class_students m JOIN class_teachers ct "
            " ON ct.class_id=m.class_id WHERE m.student_id=s.id AND ct.teacher_id=?) ORDER BY s.name", (u.id, u.id))]


@router.post("/students/{sid}/terminate")
def terminate_qr(sid: int, u: User = Depends(teacher_only)):
    """The student reported the QR missing. The QR stops working at once and the student is logged out.
    They must register again (same student ID) to get a new QR. Co-curricula and past attendance are kept."""
    with get_db() as db:
        s = own_student(db, u, sid)
        if s["qr_status"] != "active":
            raise HTTPException(409, f"{s['name']} has no working QR to terminate")
        db.execute("UPDATE users SET qr_status='terminated', qr_token=NULL, qr_printed_at=NULL WHERE id=?", (sid,))
        db.execute("DELETE FROM auth_tokens WHERE user_id=?", (sid,))
        db.execute("DELETE FROM reset_codes WHERE user_id=?", (sid,))
        audit(db, u, "qr.terminate", who(s))
    return {"ok": True}


@router.post("/students/{sid}/reset-code")
def student_reset_code(sid: int, u: User = Depends(teacher_only)):
    """Forgot password for students (who have no email): the teacher checks it is really them and gives this code."""
    with get_db() as db:
        s = own_student(db, u, sid)
        if s["qr_status"] != "active":
            raise HTTPException(409, "This student is not registered, or their QR was terminated. They should register instead.")
        code = issue_reset_code(db, sid)
        audit(db, u, "student.reset_code", who(s))
    return {"code": code, "student_no": s["username"], "name": s["name"]}


# ------------------------------------------------------------------ co-curricula (from the master list; view only)
@router.get("/classes")
def list_classes(u: User = Depends(staff)):
    """Teacher: the co-curricula they are in charge of. Admin: all of them."""
    q = ("SELECT c.id, c.name, c.category, "
         "(SELECT group_concat(t.name, ', ') FROM class_teachers ct JOIN users t ON t.id=ct.teacher_id "
         " WHERE ct.class_id=c.id) AS teachers, "
         "(SELECT COUNT(*) FROM class_students m WHERE m.class_id=c.id) AS students, "
         "(SELECT COUNT(*) FROM session_classes sc WHERE sc.class_id=c.id) AS sessions FROM classes c")
    args: list = []
    if u.role == "teacher":
        q += " WHERE EXISTS(SELECT 1 FROM class_teachers ct WHERE ct.class_id=c.id AND ct.teacher_id=?)"
        args.append(u.id)
    with get_db() as db:
        return [dict(r) for r in db.execute(q + " ORDER BY c.category='', c.category, c.name", args)]


@router.get("/classes/{cid}")
def class_detail(cid: int, u: User = Depends(staff)):
    with get_db() as db:
        c = own_class(db, u, cid)
        teachers = [dict(r) for r in db.execute(
            "SELECT t.id, t.name, t.username, t.position FROM class_teachers ct JOIN users t ON t.id=ct.teacher_id "
            "WHERE ct.class_id=? ORDER BY t.name", (cid,))]
        students = [dict(r) for r in db.execute(
            "SELECT s.id, s.username AS student_no, s.name, s.class_name, s.qr_status, "
            "EXISTS(SELECT 1 FROM photos p WHERE p.user_id=s.id) AS has_photo FROM class_students m "
            "JOIN users s ON s.id=m.student_id WHERE m.class_id=? ORDER BY s.name", (cid,))]
        sessions = [dict(r) for r in db.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM attendance a WHERE a.session_id=s.id) AS present, "
            "(SELECT group_concat(c2.name, ', ') FROM session_classes x JOIN classes c2 ON c2.id=x.class_id "
            " WHERE x.session_id=s.id) AS classes "
            "FROM sessions s JOIN session_classes sc ON sc.session_id=s.id WHERE sc.class_id=? "
            "ORDER BY s.session_date DESC, s.start_time DESC, s.id DESC", (cid,))]
    return {"id": c["id"], "name": c["name"], "category": c["category"], "teachers": teachers, "students": students,
            "sessions": sessions}


# ------------------------------------------------------------------ sessions and the calendar
class SessionIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    venue: str = Field(min_length=1, max_length=100)
    session_date: date
    start_time: str = Field(default="", pattern=TIME)
    end_time: str = Field(default="", pattern=TIME)
    class_ids: list[int] = Field(min_length=1, max_length=30)


def _check_classes(db, u: User, ids: list[int]) -> list[int]:
    """Every co-curriculum in a session must be one this teacher is in charge of."""
    ids = sorted(set(ids))
    mine = {r["class_id"] for r in db.execute("SELECT class_id FROM class_teachers WHERE teacher_id=?", (u.id,))}
    if not set(ids) <= mine:
        raise HTTPException(403, "You can only create sessions for the co-curricula you are in charge of")
    return ids


def _check_times(body: SessionIn) -> None:
    if body.start_time and body.end_time and body.end_time <= body.start_time:
        raise HTTPException(400, "The end time must be after the start time")


def _check_overlap(db, ids: list[int], body: SessionIn, except_sid: int = 0) -> None:
    """A co-curriculum can't have two sessions at the same time: each would expect every member, so students in
    the other hall would show as absent. A split class (Hall A / Hall B) is ONE session that every teacher in
    charge scans into from their own device. A missing time counts as the whole day."""
    start, end = body.start_time or "00:00", body.end_time or "23:59"
    q = ",".join("?" * len(ids))
    for s in db.execute(
            f"SELECT DISTINCT s.*, t.name AS creator, c.name AS cls FROM sessions s "
            f"JOIN session_classes sc ON sc.session_id=s.id JOIN classes c ON c.id=sc.class_id "
            f"LEFT JOIN users t ON t.id=s.created_by "
            f"WHERE s.session_date=? AND s.id<>? AND sc.class_id IN ({q}) ORDER BY s.start_time",
            [body.session_date.isoformat(), except_sid, *ids]):
        if start < (s["end_time"] or "23:59") and (s["start_time"] or "00:00") < end:
            when = s["start_time"] + (f"–{s['end_time']}" if s["end_time"] else "") or "all day"
            raise HTTPException(409, {
                "message": f"{s['cls']} already has a session at that time: {s['title']}, {when}, {s['venue']}"
                           f"{' (created by ' + s['creator'] + ')' if s['creator'] else ''}. Teachers in charge scan into "
                           f"the same session from their own devices, each choosing their own venue, so join that session "
                           f"instead of creating a second one.",
                "session_id": s["id"]})


@router.post("/sessions")
def create_session(body: SessionIn, u: User = Depends(teacher_only)):
    _check_times(body)
    with get_db() as db:
        ids = _check_classes(db, u, body.class_ids)
        _check_overlap(db, ids, body)
        sid = db.execute("INSERT INTO sessions(title,venue,session_date,start_time,end_time,created_by,created_at) "
                         "VALUES (?,?,?,?,?,?,?)", (body.title.strip(), body.venue.strip(), body.session_date.isoformat(),
                                                    body.start_time, body.end_time, u.id, now_iso())).lastrowid
        db.executemany("INSERT INTO session_classes(session_id, class_id) VALUES (?,?)", [(sid, c) for c in ids])
        audit(db, u, "session.create", session_label(db, sid))
    return {"id": sid}


@router.put("/sessions/{sid}")
def update_session(sid: int, body: SessionIn, u: User = Depends(teacher_only)):
    """Reschedule: change title, venue, date, time or the co-curricula taking part."""
    _check_times(body)
    with get_db() as db:
        own_session(db, u, sid)
        ids = _check_classes(db, u, body.class_ids)
        _check_overlap(db, ids, body, except_sid=sid)
        before = session_label(db, sid)
        db.execute("UPDATE sessions SET title=?, venue=?, session_date=?, start_time=?, end_time=? WHERE id=?",
                   (body.title.strip(), body.venue.strip(), body.session_date.isoformat(), body.start_time,
                    body.end_time, sid))
        db.execute("DELETE FROM session_classes WHERE session_id=?", (sid,))
        db.executemany("INSERT INTO session_classes(session_id, class_id) VALUES (?,?)", [(sid, c) for c in ids])
        after = session_label(db, sid)
        if after != before:
            audit(db, u, "session.edit", after, f"was: {before}")
    return {"ok": True}


@router.get("/sessions")
def calendar(start: date, end: date, u: User = Depends(teacher_only)):
    """Sessions between two dates (inclusive) of the co-curricula this teacher is in charge of."""
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT s.*, (SELECT group_concat(c.name, ', ') FROM session_classes x JOIN classes c ON c.id=x.class_id "
            " WHERE x.session_id=s.id) AS classes, "
            "(SELECT COUNT(*) FROM attendance a WHERE a.session_id=s.id) AS present "
            "FROM sessions s WHERE s.session_date BETWEEN ? AND ? "
            "AND EXISTS(SELECT 1 FROM session_classes sc JOIN class_teachers ct ON ct.class_id=sc.class_id "
            "WHERE sc.session_id=s.id AND ct.teacher_id=?) ORDER BY s.session_date, s.start_time, s.id",
            (start.isoformat(), end.isoformat(), u.id))]


def session_rows(db, sid: int) -> list[dict]:
    """Every student in any of the session's co-curricula, present or absent."""
    return [dict(r) for r in db.execute(
        "SELECT st.id AS student_id, st.username AS student_no, st.name, st.class_name, st.qr_status, "
        "EXISTS(SELECT 1 FROM photos p WHERE p.user_id=st.id) AS has_photo, "
        "group_concat(c.name, ', ') AS classes, a.checked_in_at, a.venue AS scan_venue, sb.name AS scanned_by "
        "FROM session_classes sc JOIN class_students m ON m.class_id=sc.class_id "
        "JOIN classes c ON c.id=sc.class_id JOIN users st ON st.id=m.student_id "
        "LEFT JOIN attendance a ON a.session_id=sc.session_id AND a.student_id=st.id "
        "LEFT JOIN users sb ON sb.id=a.scanned_by "
        "WHERE sc.session_id=? GROUP BY st.id ORDER BY st.name", (sid,))]


def minutes_since(iso: str) -> float:
    then = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 60


@router.get("/sessions/{sid}")
def session_detail(sid: int, u: User = Depends(teacher_only)):
    with get_db() as db:
        s = own_session(db, u, sid)
        classes = session_classes(db, sid)
        teachers = [r["name"] for r in db.execute(
            "SELECT DISTINCT t.name FROM session_classes sc JOIN class_teachers ct ON ct.class_id=sc.class_id "
            "JOIN users t ON t.id=ct.teacher_id WHERE sc.session_id=? ORDER BY t.name", (sid,))]
        rows = session_rows(db, sid)
    for r in rows:
        r["can_undo"] = bool(r["checked_in_at"]) and not s["closed"] and minutes_since(r["checked_in_at"]) <= UNDO_MINUTES
    present = sum(1 for r in rows if r["checked_in_at"])
    unregistered = sum(1 for r in rows if not r["checked_in_at"] and r["qr_status"] == "unregistered")
    return {"session": dict(s), "classes": classes, "teachers": teachers, "rows": rows, "undo_minutes": UNDO_MINUTES,
            "present": present, "absent": len(rows) - present - unregistered, "unregistered": unregistered}


class ClosedIn(BaseModel):
    closed: bool


@router.post("/sessions/{sid}/closed")
def set_closed(sid: int, body: ClosedIn, u: User = Depends(teacher_only)):
    with get_db() as db:
        own_session(db, u, sid)
        if db.execute("UPDATE sessions SET closed=? WHERE id=? AND closed<>?",
                      (int(body.closed), sid, int(body.closed))).rowcount:
            audit(db, u, "session.close" if body.closed else "session.reopen", session_label(db, sid))
    return {"ok": True}


@router.delete("/sessions/{sid}")
def delete_session(sid: int, u: User = Depends(teacher_only)):
    with get_db() as db:
        own_session(db, u, sid)
        label = session_label(db, sid)
        n = db.execute("SELECT COUNT(*) FROM attendance WHERE session_id=?", (sid,)).fetchone()[0]
        db.execute("DELETE FROM sessions WHERE id=?", (sid,))
        audit(db, u, "session.delete", label, f"{n} check-in(s) deleted with it")
    return {"ok": True}


@router.get("/sessions/{sid}/export.csv")
def export_csv(sid: int, u: User = Depends(teacher_only)):
    with get_db() as db:
        s = own_session(db, u, sid)
        rows = session_rows(db, sid)
        audit(db, u, "session.export", session_label(db, sid))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["session", "venue", "date", "start", "end", "student_id", "name", "class_id", "co_curriculum",
                "status", "checked_in_utc", "checked_in_at_venue", "scanned_by"])
    for r in rows:
        w.writerow([s["title"], s["venue"], s["session_date"], s["start_time"], s["end_time"], r["student_no"],
                    r["name"], r["class_name"], r["classes"],
                    "present" if r["checked_in_at"] else "not registered" if r["qr_status"] == "unregistered" else "absent",
                    r["checked_in_at"] or "", r["scan_venue"] or "", r["scanned_by"] or ""])
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="session-{sid}.csv"'})


# ------------------------------------------------------------------ scanning
class ScanIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)
    venue: str = Field(default="", max_length=100)   # the scanning teacher's venue ("My venue"); '' = the session's


@router.post("/sessions/{sid}/scan")
def scan(sid: int, body: ScanIn, u: User = Depends(teacher_only)):
    """Result status: checked_in | already | not_enrolled | unknown | closed. Only checked_in records anything.
    The result carries the student's photo flag, so the teacher can see it is the right person."""
    with get_db() as db:
        s = own_session(db, u, sid)
        if s["closed"]:
            return {"status": "closed", "message": "This session is closed. Reopen it to scan."}
        st = db.execute("SELECT id, username, name, class_name, active FROM users WHERE role='student' "
                        "AND qr_status='active' AND qr_token=?", (token_from_code(body.code),)).fetchone()
        if not st or not st["active"]:
            return {"status": "unknown", "message": "QR code not recognised, or it was terminated"}
        student = {"id": st["id"], "name": st["name"], "student_no": st["username"], "class_name": st["class_name"],
                   "has_photo": has_photo(db, st["id"])}
        if not db.execute("SELECT 1 FROM session_classes sc JOIN class_students m ON m.class_id=sc.class_id "
                          "WHERE sc.session_id=? AND m.student_id=?", (sid, st["id"])).fetchone():
            return {"status": "not_enrolled", "student": student,
                    "message": f"{st['name']} is not involved in this session. Nothing was recorded."}
        t, venue = now_iso(), " ".join(body.venue.split()) or s["venue"]
        if db.execute("INSERT OR IGNORE INTO attendance(session_id,student_id,checked_in_at,scanned_by,venue) "
                      "VALUES (?,?,?,?,?)", (sid, st["id"], t, u.id, venue)).rowcount == 0:
            prev = db.execute("SELECT a.checked_in_at, a.venue, t.name AS scanner FROM attendance a "
                              "LEFT JOIN users t ON t.id=a.scanned_by WHERE a.session_id=? AND a.student_id=?",
                              (sid, st["id"])).fetchone()
            return {"status": "already", "student": student, "time": prev["checked_in_at"], "venue": prev["venue"],
                    "scanned_by": prev["scanner"],"message": f"{st['name']} has already checked in"}
        audit(db, u, "attendance.check_in", who(st), f"{session_label(db, sid)} · at {venue}")
    return {"status": "checked_in", "student": student, "time": t, "venue": venue, "undo_minutes": UNDO_MINUTES,
            "message": f"{st['name']} checked in successfully"}


@router.delete("/sessions/{sid}/attendance/{student_id}")
def undo_check_in(sid: int, student_id: int, u: User = Depends(teacher_only)):
    """Undo a check-in made by mistake: only while the session is open and within UNDO_MINUTES of the scan."""
    with get_db() as db:
        s = own_session(db, u, sid)
        a = db.execute("SELECT a.checked_in_at, st.name, st.username FROM attendance a JOIN users st ON st.id=a.student_id "
                       "WHERE a.session_id=? AND a.student_id=?", (sid, student_id)).fetchone()
        if not a:
            raise HTTPException(404, "This student has not checked in to this session")
        if s["closed"] or minutes_since(a["checked_in_at"]) > UNDO_MINUTES:
            raise HTTPException(409, f"A check-in can only be undone within {UNDO_MINUTES} minutes, while the session is open")
        db.execute("DELETE FROM attendance WHERE session_id=? AND student_id=?", (sid, student_id))
        audit(db, u, "attendance.undo", who(a), session_label(db, sid))
    return {"ok": True}


# ------------------------------------------------------------------ achievements (teachers record them)
class AchievementIn(BaseModel):
    student_id: int
    class_id: int
    year: int = Field(ge=1990, le=2100)
    level: str = Field(min_length=1, max_length=40)
    award: str = Field(min_length=1, max_length=100)


@router.get("/achievements")
def my_achievements(u: User = Depends(teacher_only)):
    """Achievements recorded for the co-curricula this teacher is in charge of."""
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT a.id, a.year, a.activity, a.level, a.award, a.class_id, s.username AS student_no, s.name, s.class_name, "
            "t.name AS added_by FROM achievements a JOIN users s ON s.id=a.student_id LEFT JOIN users t ON t.id=a.added_by "
            "WHERE a.class_id IN (SELECT class_id FROM class_teachers WHERE teacher_id=?) "
            "ORDER BY a.year DESC, s.name", (u.id,))]


@router.post("/achievements")
def add_achievement(body: AchievementIn, u: User = Depends(teacher_only)):
    """For a member of one of the teacher's own co-curricula; the activity is that co-curriculum."""
    with get_db() as db:
        c = own_class(db, u, body.class_id)
        s = db.execute("SELECT u.* FROM class_students m JOIN users u ON u.id=m.student_id "
                       "WHERE m.class_id=? AND m.student_id=?", (c["id"], body.student_id)).fetchone()
        if not s:
            raise HTTPException(404, f"This student is not a member of {c['name']}")
        level = LEVELS.get(body.level.strip().lower(), " ".join(body.level.split()))
        award = " ".join(body.award.split())
        if db.execute("INSERT OR IGNORE INTO achievements(student_id, year, activity, level, award, class_id, added_by, "
                      "created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (s["id"], body.year, c["name"], level, award, c["id"], u.id, now_iso())).rowcount == 0:
            raise HTTPException(409, "This achievement is already recorded")
        audit(db, u, "achievement.add", who(s), f"{body.year} {c['name']} · {level} · {award}")
    return {"ok": True}


@router.delete("/achievements/{aid}")
def delete_achievement(aid: int, u: User = Depends(teacher_only)):
    with get_db() as db:
        a = db.execute("SELECT a.*, s.username, s.name FROM achievements a JOIN users s ON s.id=a.student_id "
                       "WHERE a.id=? AND a.class_id IN (SELECT class_id FROM class_teachers WHERE teacher_id=?)",
                       (aid, u.id)).fetchone()
        if not a:
            raise HTTPException(404, "Achievement not found, or not for a co-curriculum you are in charge of")
        db.execute("DELETE FROM achievements WHERE id=?", (aid,))
        audit(db, u, "achievement.remove", who(a), f"{a['year']} {a['activity']} · {a['level']} · {a['award']}")
    return {"ok": True}
