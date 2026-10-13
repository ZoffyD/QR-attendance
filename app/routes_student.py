"""Students: register once (student ID, name, password), print their QR once, and see what they attended.
Registration only works for a student ID and name that are on the school's master list; the class ID shown
in the profile comes from that list. A student can register again only after a teacher terminates their QR."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import ratelimit
from .accounts import COCU, norm
from .audit import audit
from .db import get_db, now_iso
from .security import User, create_login, hash_password, student_only
from .util import PREFIX, new_qr_token, qr_svg

router = APIRouter(prefix="/api")
NOT_ON_LIST = ("Your student ID and name do not match the school's master list. Check the spelling of your full "
               "name and your student ID, or ask the admin to add you.")


class RegisterIn(BaseModel):
    student_no: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


@router.post("/register/student")
def register(body: RegisterIn, request: Request):
    ip = request.client.host if request.client else "?"
    ratelimit.check(f"register:{ip}", 10, 900)
    no = body.student_no.strip()
    with get_db() as db:
        s = db.execute("SELECT * FROM users WHERE role='student' AND username=?", (no,)).fetchone()
        if not s or norm(s["name"]) != norm(body.name):   # same answer for a wrong ID and a wrong name
            ratelimit.record(f"register:{ip}")
            raise HTTPException(400, NOT_ON_LIST)
        if s["qr_status"] == "active":
            raise HTTPException(409, "This student ID is already registered, and a student can register only once. "
                                     "Log in instead. Lost your QR? Ask your teacher to terminate it, then register again. "
                                     "Forgot your password? Use Forgot password.")
        if not s["active"]:
            raise HTTPException(403, "This account has been disabled. Please contact the admin.")
        # first time, or again after a teacher terminated the QR: classes and past attendance stay
        db.execute("UPDATE users SET pw_hash=?, qr_token=?, qr_status='active', qr_printed_at=NULL, registered_at=? "
                   "WHERE id=?", (hash_password(body.password), new_qr_token(), now_iso(), s["id"]))
        audit(db, s, "student.register_again" if s["qr_status"] == "terminated" else "student.register",
              f"{s['name']} ({s['username']})")
        token = create_login(db, s["id"])
    return {"token": token, "role": "student", "name": s["name"], "class_name": s["class_name"]}


@router.get("/student/me")
def me(u: User = Depends(student_only)):
    with get_db() as db:
        s = db.execute("SELECT * FROM users WHERE id=?", (u.id,)).fetchone()
        classes = [dict(r) for r in db.execute(
            "SELECT c.name, c.category, (SELECT group_concat(t.name, ', ') FROM class_teachers ct "
            " JOIN users t ON t.id=ct.teacher_id WHERE ct.class_id=c.id) AS teachers "
            "FROM class_students m JOIN classes c ON c.id=m.class_id WHERE m.student_id=? ORDER BY c.name", (u.id,))]
        achievements = [dict(r) for r in db.execute(
            "SELECT year, activity, level, award FROM achievements WHERE student_id=? ORDER BY year DESC, activity", (u.id,))]
        photo = db.execute("SELECT 1 FROM photos WHERE user_id=?", (u.id,)).fetchone() is not None
    cocu = {cat: next((c for c in classes if c["category"] == cat), None) for cat in COCU}
    return {"id": s["id"], "student_no": s["username"], "name": s["name"], "class_name": s["class_name"],
            "cocurricula": [{**(v or {"name": "", "teachers": ""}), "category": COCU[k]} for k, v in cocu.items()],
            "achievements": achievements, "has_photo": photo,
            "registered_at": s["registered_at"], "qr_printed_at": s["qr_printed_at"]}


@router.post("/student/qr")
def get_qr_once(u: User = Depends(student_only)):
    """The QR is handed out once only, so a student cannot reprint copies for friends to scan for them."""
    with get_db() as db:
        n = db.execute("UPDATE users SET qr_printed_at=? WHERE id=? AND qr_printed_at IS NULL",
                       (now_iso(), u.id)).rowcount
        s = db.execute("SELECT * FROM users WHERE id=?", (u.id,)).fetchone()
        if n:
            audit(db, u, "student.qr_printed", f"{s['name']} ({s['username']})")
    if not n:
        raise HTTPException(409, "Your QR code was already printed. If it is lost, ask your teacher to terminate it, "
                                 "then register again to get a new one.")
    return {"code": PREFIX + s["qr_token"], "qr_svg": qr_svg(s["qr_token"]), "name": s["name"],
            "student_no": s["username"], "class_name": s["class_name"]}


@router.get("/student/attendance/summary")
def my_summary(u: User = Depends(student_only)):
    """Per co-curriculum: sessions held so far (up to today) and how many the student attended."""
    today = date.today().isoformat()
    with get_db() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT c.name, c.category, "
            "(SELECT COUNT(*) FROM session_classes sc JOIN sessions s ON s.id=sc.session_id "
            " WHERE sc.class_id=c.id AND s.session_date<=?) AS held, "
            "(SELECT COUNT(*) FROM session_classes sc JOIN sessions s ON s.id=sc.session_id "
            " JOIN attendance a ON a.session_id=s.id AND a.student_id=m.student_id "
            " WHERE sc.class_id=c.id AND s.session_date<=?) AS attended "
            "FROM class_students m JOIN classes c ON c.id=m.class_id WHERE m.student_id=? "
            "ORDER BY c.category='', c.category, c.name", (today, today, u.id))]
    for r in rows:
        r["percent"] = round(100 * r["attended"] / r["held"], 1) if r["held"] else None
    return rows


@router.get("/student/attendance")
def my_attendance(u: User = Depends(student_only)):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT s.title, COALESCE(NULLIF(a.venue, ''), s.venue) AS venue, s.session_date, s.start_time, s.end_time, a.checked_in_at, "
            "(SELECT group_concat(c.name, ', ') FROM session_classes sc JOIN classes c ON c.id=sc.class_id "
            " JOIN class_students m ON m.class_id=c.id AND m.student_id=a.student_id WHERE sc.session_id=s.id) AS classes "
            "FROM attendance a JOIN sessions s ON s.id=a.session_id WHERE a.student_id=? "
            "ORDER BY a.checked_in_at DESC", (u.id,))]
