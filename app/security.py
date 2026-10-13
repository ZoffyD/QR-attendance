import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from . import config
from .db import get_db, now_iso


@dataclass
class User:
    id: int
    role: str          # 'admin' | 'teacher' | 'student'
    username: str
    name: str


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + digest.hex()


def check_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


def expiry(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_login(db, user_id: int) -> str:
    token = "tok_" + secrets.token_urlsafe(24)
    db.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (now_iso(),))
    db.execute("INSERT INTO auth_tokens(token_hash, user_id, expires_at) VALUES (?,?,?)",
               (hash_key(token), user_id, expiry(hours=config.LOGIN_HOURS)))
    return token


def issue_reset_code(db, user_id: int) -> str:
    """A 6-digit one-time code for forgot password. Replaces any older code for this user."""
    code = f"{secrets.randbelow(10**6):06d}"
    db.execute("INSERT INTO reset_codes(user_id, requested_at, code_hash, expires_at, attempts) VALUES (?,?,?,?,0) "
               "ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash, expires_at=excluded.expires_at, attempts=0",
               (user_id, now_iso(), hash_key(code), expiry(minutes=config.RESET_MINUTES)))
    return code


def bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in")
    return authorization[7:].strip()


def current_user(authorization: str | None = Header(default=None)) -> User:
    with get_db() as db:
        u = db.execute("SELECT u.id, u.role, u.username, u.name FROM auth_tokens t JOIN users u ON u.id=t.user_id "
                       "WHERE t.token_hash=? AND t.expires_at > ? AND u.active=1 AND u.approved=1 "
                       "AND u.qr_status='active'", (hash_key(bearer(authorization)), now_iso())).fetchone()
    if not u:
        raise HTTPException(401, "Your login has expired. Please log in again.")
    return User(u["id"], u["role"], u["username"], u["name"])


def require(*roles: str):
    def dep(authorization: str | None = Header(default=None)) -> User:
        u = current_user(authorization)
        if u.role not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return u
    return dep


admin_only = require("admin")
teacher_only = require("teacher")   # day-to-day work: sessions, scanning, achievements, student QR and passwords
staff = require("teacher", "admin")   # viewing: the admin can look at what teachers see
student_only = require("student")
