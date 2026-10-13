"""Attendance reports over a date range.

- Teachers: a summary of the co-curricula they are in charge of, and per co-curriculum each student's attendance.
  They never see other teachers' co-curricula.
- Admin: the overall summary only (every co-curriculum, totals); no per-student detail.

Rules:
- Only sessions from start to end that have already happened (up to today) count, so planned sessions later in
  the term do not lower anyone's percentage.
- A student counts for a class's sessions while they are in the class now (current members).
- Students who have not registered yet (no QR, so they cannot be scanned) are listed but left out of the %.
- A student is present at a session when they checked in, whichever teacher scanned them.
"""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .audit import audit
from .db import get_db
from .routes_teacher import own_class
from .security import User, staff, teacher_only

router = APIRouter(prefix="/api/reports")


def _range(start: date | None, end: date | None) -> tuple[str, str]:
    today = date.today()
    start = start or date(today.year, 1, 1)
    end = min(end or today, today)
    if end < start:
        raise HTTPException(400, "The end date must be on or after the start date")
    return start.isoformat(), end.isoformat()


def pct(present: int, possible: int) -> float | None:
    return round(100 * present / possible, 1) if possible else None


@router.get("/classes")
def class_summary(start: date | None = None, end: date | None = None, u: User = Depends(staff)):
    """Every co-curriculum the user is in charge of (admin: all) with sessions held and average attendance,
    plus overall totals."""
    a, b = _range(start, end)
    sql = ("WITH held AS (SELECT sc.class_id, s.id FROM session_classes sc JOIN sessions s ON s.id=sc.session_id "
           "              WHERE s.session_date BETWEEN ? AND ?) "
           "SELECT c.id, c.name, c.category, "
           "(SELECT group_concat(t.name, ', ') FROM class_teachers ct JOIN users t ON t.id=ct.teacher_id "
           " WHERE ct.class_id=c.id) AS teachers, "
           "(SELECT COUNT(*) FROM class_students m JOIN users st ON st.id=m.student_id "
           " WHERE m.class_id=c.id AND st.qr_status<>'unregistered') AS students, "
           "(SELECT COUNT(*) FROM class_students m JOIN users st ON st.id=m.student_id "
           " WHERE m.class_id=c.id AND st.qr_status='unregistered') AS unregistered, "
           "(SELECT COUNT(*) FROM held WHERE held.class_id=c.id) AS sessions, "
           "(SELECT COUNT(*) FROM held JOIN attendance att ON att.session_id=held.id "
           " JOIN class_students m ON m.class_id=held.class_id AND m.student_id=att.student_id "
           " WHERE held.class_id=c.id) AS present "
           "FROM classes c")
    args: list = [a, b]
    if u.role == "teacher":
        sql += " WHERE EXISTS(SELECT 1 FROM class_teachers ct WHERE ct.class_id=c.id AND ct.teacher_id=?)"
        args.append(u.id)
    with get_db() as db:
        rows = [dict(r) for r in db.execute(sql + " ORDER BY c.category='', c.category, c.name", args)]
        held = db.execute("SELECT COUNT(*) FROM sessions s WHERE s.session_date BETWEEN ? AND ?" + (
            " AND EXISTS(SELECT 1 FROM session_classes sc JOIN class_teachers ct ON ct.class_id=sc.class_id "
            "WHERE sc.session_id=s.id AND ct.teacher_id=?)" if u.role == "teacher" else ""),
            [a, b, u.id] if u.role == "teacher" else [a, b]).fetchone()[0]
    for r in rows:
        r["possible"] = r["students"] * r["sessions"]
        r["percent"] = pct(r["present"], r["possible"])
    present, possible = sum(r["present"] for r in rows), sum(r["possible"] for r in rows)
    below = sum(1 for r in rows if r["percent"] is not None and r["percent"] < 75)
    return {"start": a, "end": b, "classes": rows,
            "overall": {"sessions": held, "present": present, "possible": possible, "percent": pct(present, possible),
                        "below_75": below}}


def class_report_data(db, u: User, cid: int, start: date | None, end: date | None) -> dict:
    c = own_class(db, u, cid)
    a, b = _range(start, end)
    sessions = [dict(r) for r in db.execute(
        "SELECT s.id, s.title, s.venue, s.session_date, s.start_time, s.end_time, "
        "(SELECT COUNT(*) FROM attendance att JOIN class_students m ON m.student_id=att.student_id AND m.class_id=? "
        " WHERE att.session_id=s.id) AS present "
        "FROM sessions s JOIN session_classes sc ON sc.session_id=s.id "
        "WHERE sc.class_id=? AND s.session_date BETWEEN ? AND ? ORDER BY s.session_date, s.start_time, s.id",
        (cid, cid, a, b))]
    ids = [s["id"] for s in sessions]
    students = [dict(r) for r in db.execute(
        "SELECT st.id, st.username AS student_no, st.name, st.class_name, st.qr_status FROM class_students m "
        "JOIN users st ON st.id=m.student_id WHERE m.class_id=? ORDER BY st.name", (cid,))]
    marks: dict[int, dict[int, str]] = {}
    if ids:
        for r in db.execute(f"SELECT session_id, student_id, checked_in_at FROM attendance "
                            f"WHERE session_id IN ({','.join('?' * len(ids))})", ids):
            marks.setdefault(r["student_id"], {})[r["session_id"]] = r["checked_in_at"]
    for s in students:
        mine = marks.get(s["id"], {})
        s["registered"] = s.pop("qr_status") != "unregistered"   # not registered = no QR yet: left out of the %
        s["attended"] = len(mine)
        s["percent"] = pct(len(mine), len(ids)) if s["registered"] else None
        s["last_seen"] = max(mine.values()) if mine else None
        s["sessions"] = [sid for sid in ids if sid in mine]
    counted = sum(1 for s in students if s["registered"])
    for s in sessions:
        s["percent"] = pct(s["present"], counted)
    possible = len(ids) * counted
    present = sum(s["attended"] for s in students if s["registered"])
    return {"id": c["id"], "name": c["name"], "category": c["category"], "start": a, "end": b, "sessions": sessions,
            "students": students, "counted": counted, "unregistered": len(students) - counted,
            "present": present, "possible": possible, "percent": pct(present, possible)}


@router.get("/classes/{cid}")
def class_report(cid: int, start: date | None = None, end: date | None = None, u: User = Depends(teacher_only)):
    with get_db() as db:
        return class_report_data(db, u, cid, start, end)


@router.get("/classes/{cid}/export.csv")
def class_report_csv(cid: int, start: date | None = None, end: date | None = None, u: User = Depends(teacher_only)):
    """One row per student, one column per session (1 = present, 0 = absent), then the totals. Opens in Excel."""
    with get_db() as db:
        r = class_report_data(db, u, cid, start, end)
        audit(db, u, "report.export", r["name"], f"{r['start']} to {r['end']}")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["class", r["name"], "from", r["start"], "to", r["end"]])
    w.writerow(["student_id", "name", "class_id",
                *[f"{s['session_date']} {s['start_time']} {s['title']}".replace("  ", " ") for s in r["sessions"]],
                "attended", "sessions", "percent"])
    for s in r["students"]:
        got = set(s["sessions"])
        w.writerow([s["student_no"], s["name"], s["class_name"], *[1 if x["id"] in got else 0 for x in r["sessions"]],
                    s["attended"], len(r["sessions"]),
                    "not registered" if not s["registered"] else "" if s["percent"] is None else s["percent"]])
    w.writerow(["", "present", "", *[x["present"] for x in r["sessions"]], r["present"], r["possible"],
                "" if r["percent"] is None else r["percent"]])
    safe = "".join(ch if ch.isalnum() else "_" for ch in r["name"]).strip("_") or "class"
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="attendance-{safe}-{r["start"]}-{r["end"]}.csv"'})
