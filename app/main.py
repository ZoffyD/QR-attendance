import asyncio
import base64
import os
import re
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import backup, config, mailer, ratelimit
from .accounts import EMAIL, email_taken, norm
from .audit import audit
from .db import get_db, init_db, now_iso
from .security import (User, bearer, check_password, create_login, current_user, hash_key, hash_password,
                       issue_reset_code)

STATIC = os.path.join(os.path.dirname(__file__), "static")
MAX_CODE_TRIES = 5
_DUMMY_HASH = hash_password("not-a-real-password")   # a wrong username takes as long to refuse as a wrong password


def seed_admin() -> None:
    """The first start creates the admin account. After that the admin changes the password in the app."""
    with get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            return
        pw = config.ADMIN_PASSWORD or secrets.token_urlsafe(9)
        db.execute("INSERT INTO users(role,username,name,email,pw_hash,created_at) VALUES ('admin','admin','Administrator',?,?,?)",
                   (config.ADMIN_EMAIL, hash_password(pw), now_iso()))
    print(f"[attendance] Admin account created. Username: admin  Password: "
          f"{'(from ATT_ADMIN_PASSWORD)' if config.ADMIN_PASSWORD else pw}", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_admin()
    task = asyncio.create_task(backup.scheduler())
    yield
    task.cancel()


app = FastAPI(title="QR Attendance", version="3.0.0", lifespan=lifespan)
from .routes_admin import router as admin_router  # noqa: E402
from .routes_reports import router as reports_router  # noqa: E402
from .routes_student import router as student_router  # noqa: E402
from .routes_teacher import router as teacher_router  # noqa: E402
app.include_router(admin_router)
app.include_router(teacher_router)
app.include_router(student_router)
app.include_router(reports_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
    return resp


# Each role has its own address. Students are the most users, so the bare address opens the student portal;
# teachers and the admin are given their own links, so students never see those log-ins.
@app.get("/")
def home():
    return RedirectResponse("/student")


@app.get("/student")
@app.get("/teacher")
@app.get("/admin")
def portal_login():
    return FileResponse(os.path.join(STATIC, "login.html"))


@app.get("/student/register")
@app.get("/teacher/register")
def portal_register():
    return FileResponse(os.path.join(STATIC, "register.html"))


@app.get("/student/forgot")
@app.get("/teacher/forgot")
@app.get("/admin/forgot")
def portal_forgot():
    return FileResponse(os.path.join(STATIC, "forgot.html"))


@app.get("/student/app")
def student_portal():
    return FileResponse(os.path.join(STATIC, "student.html"))


@app.get("/teacher/app")
def teacher_portal():
    return FileResponse(os.path.join(STATIC, "teacher.html"))


@app.get("/admin/app")
def admin_portal():
    return FileResponse(os.path.join(STATIC, "admin.html"))


@app.get("/healthz")
def healthz():
    with get_db() as db:
        db.execute("SELECT 1").fetchone()
    return {"ok": True}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


# ------------------------------------------------------------------ log in / out (every role)
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)    # teacher/admin username, or student ID
    password: str = Field(max_length=200)
    role: str | None = Field(default=None, pattern="^(admin|teacher|student)$")   # which login page was used


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    key = f"login:{client_ip(request)}:{body.username.strip().lower()}"
    ratelimit.check(key, 10, 600)
    with get_db() as db:
        u = db.execute("SELECT * FROM users WHERE username=?", (body.username.strip(),)).fetchone()
        if not (check_password(body.password, u["pw_hash"] if u else _DUMMY_HASH) and u is not None):
            ratelimit.record(key)
            raise HTTPException(401, "Wrong username or password")
        if body.role and u["role"] != body.role:
            raise HTTPException(403, f"This is a {u['role']} account. Please use the {u['role'].title()} login.")
        if not u["active"]:
            raise HTTPException(403, "This account has been disabled. Please contact the admin.")
        if u["qr_status"] == "terminated":
            raise HTTPException(403, "Your QR code was terminated by your teacher. Please register again to get a new one.")
        token = create_login(db, u["id"])
    return {"token": token, "role": u["role"], "name": u["name"]}


@app.post("/api/logout")
def logout(request: Request):
    try:
        token = bearer(request.headers.get("authorization"))
    except HTTPException:
        return {"ok": True}
    with get_db() as db:
        db.execute("DELETE FROM auth_tokens WHERE token_hash=?", (hash_key(token),))
    return {"ok": True}


@app.get("/api/me")
def me(u: User = Depends(current_user)):
    with get_db() as db:
        return dict(db.execute("SELECT id, role, username, name, email, class_name, position, "
                               "EXISTS(SELECT 1 FROM photos p WHERE p.user_id=users.id) AS has_photo "
                               "FROM users WHERE id=?", (u.id,)).fetchone())


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@app.post("/api/me/password")
def change_password(body: ChangePasswordIn, u: User = Depends(current_user)):
    with get_db() as db:
        row = db.execute("SELECT pw_hash FROM users WHERE id=?", (u.id,)).fetchone()
        if not check_password(body.current_password, row["pw_hash"]):
            raise HTTPException(400, "Your current password is wrong")
        db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(body.new_password), u.id))
        audit(db, u, "password.change")
    return {"ok": True}


# ------------------------------------------------------------------ teacher registration (like students)
class TeacherRegisterIn(BaseModel):
    teacher_no: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=EMAIL)
    password: str = Field(min_length=8, max_length=200)


@app.post("/api/register/teacher")
def register_teacher(body: TeacherRegisterIn, request: Request):
    """A teacher registers once with the teacher ID and name from the admin's teacher master list. Their
    position and co-curricula come from that list, so they cannot choose the wrong ones."""
    ip = client_ip(request)
    ratelimit.check(f"register:{ip}", 10, 900)
    with get_db() as db:
        t = db.execute("SELECT * FROM users WHERE role='teacher' AND username=?", (body.teacher_no.strip(),)).fetchone()
        if not t or norm(t["name"]) != norm(body.name):   # same answer for a wrong ID and a wrong name
            ratelimit.record(f"register:{ip}")
            raise HTTPException(400, "Your teacher ID and name do not match the school's teacher list. "
                                     "Check the spelling, or ask the admin.")
        if t["qr_status"] != "unregistered":
            raise HTTPException(409, "This teacher ID is already registered. Log in instead, or use Forgot password.")
        if not t["active"]:
            raise HTTPException(403, "This account has been disabled. Please contact the admin.")
        if email_taken(db, body.email.strip(), t["id"]):
            raise HTTPException(409, "That email is already used by another account")
        db.execute("UPDATE users SET pw_hash=?, email=?, qr_status='active', registered_at=? WHERE id=?",
                   (hash_password(body.password), body.email.strip(), now_iso(), t["id"]))
        audit(db, t, "teacher.register", f"{t['name']} ({t['username']})")
        token = create_login(db, t["id"])
    return {"token": token, "role": "teacher", "name": t["name"]}


# ------------------------------------------------------------------ profile pictures (students and teachers)
PHOTO_TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG", "image/webp": b"RIFF"}
MAX_PHOTO = 400_000


class PhotoIn(BaseModel):
    data_url: str = Field(min_length=20, max_length=600_000)   # data:image/jpeg;base64,... (the page shrinks it first)


@app.post("/api/me/photo")
def upload_photo(body: PhotoIn, u: User = Depends(current_user)):
    if u.role == "admin":
        raise HTTPException(403, "Only students and teachers have a profile picture")
    m = re.fullmatch(r"data:(image/[a-z]+);base64,([A-Za-z0-9+/=]+)", body.data_url.strip())
    if not m or m.group(1) not in PHOTO_TYPES:
        raise HTTPException(400, "Please choose a JPG, PNG or WebP picture")
    try:
        data = base64.b64decode(m.group(2), validate=True)
    except ValueError:
        raise HTTPException(400, "The picture could not be read") from None
    if not data.startswith(PHOTO_TYPES[m.group(1)]) or len(data) > MAX_PHOTO:
        raise HTTPException(400, "The picture could not be read, or it is too big")
    with get_db() as db:
        db.execute("INSERT INTO photos(user_id, mime, data, updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE "
                   "SET mime=excluded.mime, data=excluded.data, updated_at=excluded.updated_at",
                   (u.id, m.group(1), data, now_iso()))
        audit(db, u, "photo.change")
    return {"ok": True}


@app.delete("/api/me/photo")
def delete_photo(u: User = Depends(current_user)):
    with get_db() as db:
        if db.execute("DELETE FROM photos WHERE user_id=?", (u.id,)).rowcount:
            audit(db, u, "photo.remove")
    return {"ok": True}


@app.get("/api/photos/{uid}")
def get_photo(uid: int, u: User = Depends(current_user)):
    """Who can see a picture: the person themself; the admin; a teacher for their own students and for the
    teachers who share a co-curriculum with them."""
    with get_db() as db:
        allowed = uid == u.id or u.role == "admin" or (u.role == "teacher" and db.execute(
            "SELECT 1 FROM class_teachers ct WHERE ct.teacher_id=? AND ct.class_id IN ("
            " SELECT class_id FROM class_students WHERE student_id=? UNION "
            " SELECT class_id FROM class_teachers WHERE teacher_id=?)", (u.id, uid, uid)).fetchone())
        p = db.execute("SELECT mime, data FROM photos WHERE user_id=?", (uid,)).fetchone() if allowed else None
    if not p:
        raise HTTPException(404, "No picture")
    return Response(p["data"], media_type=p["mime"])


# ------------------------------------------------------------------ forgot password (every role)
class ForgotIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=120)   # username, student ID or email


FORGOT_MSG = ("Request received. Teachers and admin: a 6-digit code has been sent to your email. "
              "Students: ask your teacher or the admin for your reset code. Then enter the code below.")


@app.post("/api/forgot-password")
def forgot_password(body: ForgotIn, request: Request):
    """Always answers the same way, so nobody can use it to find out which accounts exist."""
    ratelimit.check(f"forgot:{client_ip(request)}", 10, 900)
    ratelimit.record(f"forgot:{client_ip(request)}")
    ident = body.identifier.strip()
    with get_db() as db:
        u = db.execute("SELECT * FROM users WHERE active=1 AND approved=1 AND qr_status='active' "
                       "AND (username=? OR (email<>'' AND email=?))", (ident, ident)).fetchone()
        code = None
        if u and u["role"] == "student":   # shows up in the teachers' "reset requests" list
            db.execute("INSERT INTO reset_codes(user_id, requested_at) VALUES (?,?) "
                       "ON CONFLICT(user_id) DO UPDATE SET requested_at=excluded.requested_at", (u["id"], now_iso()))
        elif u:
            code = issue_reset_code(db, u["id"])
    if code:
        mailer.send_reset_code(u["email"], u["name"], u["username"], code)
    return {"ok": True, "message": FORGOT_MSG}


class ResetIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: str = Field(min_length=8, max_length=200)


@app.post("/api/reset-password")
def reset_password(body: ResetIn, request: Request):
    ratelimit.check(f"reset:{client_ip(request)}", 20, 900)
    bad = HTTPException(400, "The code is wrong or has expired. Ask for a new one.")
    ident = body.identifier.strip()
    with get_db() as db:
        r = db.execute("SELECT r.*, u.id AS uid FROM reset_codes r JOIN users u ON u.id=r.user_id "
                       "WHERE (u.username=? OR (u.email<>'' AND u.email=?)) AND r.code_hash IS NOT NULL "
                       "AND r.expires_at > ? AND r.attempts < ?", (ident, ident, now_iso(), MAX_CODE_TRIES)).fetchone()
        if not r:
            ratelimit.record(f"reset:{client_ip(request)}")
            raise bad
        if hash_key(body.code) != r["code_hash"]:
            db.execute("UPDATE reset_codes SET attempts=attempts+1 WHERE user_id=?", (r["uid"],))
            db.commit()
            ratelimit.record(f"reset:{client_ip(request)}")
            raise bad
        db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(body.password), r["uid"]))
        db.execute("DELETE FROM reset_codes WHERE user_id=?", (r["uid"],))
        db.execute("DELETE FROM auth_tokens WHERE user_id=?", (r["uid"],))   # sign out everywhere
        audit(db, db.execute("SELECT * FROM users WHERE id=?", (r["uid"],)).fetchone(), "password.reset_with_code")
    return {"ok": True}
