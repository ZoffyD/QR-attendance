"""Activity log: who changed what, and when. The admin reads it in the Activity log tab."""
from .db import now_iso

ROLE = {"admin": "Admin", "teacher": "Teacher", "student": "Student"}


def audit(db, who, action: str, target: str = "", detail: str = "") -> None:
    """who: the logged-in User, or a users row (for registration and password resets)."""
    uid, name, role = (who.id, who.name, who.role) if hasattr(who, "id") else (who["id"], who["name"], who["role"])
    db.execute("INSERT INTO audit_log(at, actor_id, actor, action, target, detail) VALUES (?,?,?,?,?,?)",
               (now_iso(), uid, f"{name} ({ROLE.get(role, role)})", action, target[:200], detail[:500]))
