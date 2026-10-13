"""Admin: the main administrator. Uploads the school's master list (one file of students, one file of teachers)
and then only VIEWS: students, teachers, co-curricula, achievements, an overall report, the activity log and
backups. Day-to-day work (sessions, scanning, achievements, student QR and passwords) belongs to the teachers."""
import csv
import io
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import backup, config
from .accounts import COCU, check_id, upsert_student, upsert_teacher
from .audit import audit
from .db import get_db
from .security import User, admin_only

router = APIRouter(prefix="/api/admin")


@router.get("/overview")
def overview(u: User = Depends(admin_only)):
    with get_db() as db:
        one = lambda q: db.execute(q).fetchone()[0]  # noqa: E731
        counts = {
            "students": one("SELECT COUNT(*) FROM users WHERE role='student'"),
            "students_registered": one("SELECT COUNT(*) FROM users WHERE role='student' AND qr_status<>'unregistered'"),
            "teachers": one("SELECT COUNT(*) FROM users WHERE role='teacher'"),
            "teachers_registered": one("SELECT COUNT(*) FROM users WHERE role='teacher' AND qr_status<>'unregistered'"),
            "classes": one("SELECT COUNT(*) FROM classes"),
            "no_teacher": one("SELECT COUNT(*) FROM classes c WHERE NOT EXISTS "
                              "(SELECT 1 FROM class_teachers ct WHERE ct.class_id=c.id)"),
            "sessions": one("SELECT COUNT(*) FROM sessions"),
            "check_ins": one("SELECT COUNT(*) FROM attendance"),
            "achievements": one("SELECT COUNT(*) FROM achievements"),
        }
        classes = [dict(r) for r in db.execute(
            "SELECT c.id, c.name, c.category, "
            "(SELECT group_concat(t.name, ', ') FROM class_teachers ct JOIN users t ON t.id=ct.teacher_id "
            " WHERE ct.class_id=c.id) AS teachers, "
            "(SELECT COUNT(*) FROM class_students m WHERE m.class_id=c.id) AS students, "
            "(SELECT COUNT(*) FROM session_classes sc WHERE sc.class_id=c.id) AS sessions "
            "FROM classes c ORDER BY c.category='', c.category, c.name")]
    files = backup.list_backups()
    return {"counts": counts, "classes": classes,
            "backup": {"last": files[0]["created"] if files else None, "every_hours": config.BACKUP_HOURS}}


# ------------------------------------------------------------------ reading CSV files
def _key(header: str) -> str:
    """'Club / Society' -> 'club_society'"""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (header or "").strip().lower())).strip("_")


def read_csv(text: str, alias: dict, required: set, what: str) -> tuple[list[dict], set]:
    """Rows as {field: value} using alias {header key: field}. Also returns which fields the file has."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    have = {alias[_key(f)] for f in reader.fieldnames or [] if _key(f) in alias}
    if not required <= have:
        raise HTTPException(400, f"The CSV needs a header row with the columns {what}")
    rows = [{alias[_key(k)]: (v or "").strip() for k, v in raw.items() if k and _key(k) in alias} for raw in reader]
    return rows, have


def apply_rows(db, rows, apply) -> tuple[int, int, list[str]]:
    """Runs apply(row) for each row; a row that fails is undone and reported, the others still count."""
    added = updated = 0
    problems: list[str] = []
    for i, row in enumerate(rows, start=2):   # line 1 is the header
        db.execute("SAVEPOINT import_row")
        try:
            if apply(row):
                added += 1
            else:
                updated += 1
            db.execute("RELEASE import_row")
        except (HTTPException, ValueError) as exc:
            db.execute("ROLLBACK TO import_row")
            db.execute("RELEASE import_row")
            problems.append(f"line {i}: {exc.detail if isinstance(exc, HTTPException) else exc}")
    return added, updated, problems


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=5_000_000)


# ------------------------------------------------------------------ master list: students
STUDENT_ALIAS = {
    **dict.fromkeys(["student_no", "student_id", "id", "no", "matric_no"], "no"),
    **dict.fromkeys(["name", "full_name", "student_name", "nama"], "name"),
    **dict.fromkeys(["class_id", "class", "class_name", "kelas"], "cls"),
    **dict.fromkeys(["uniform_body", "uniform", "uniformed_body", "uniform_unit", "badan_beruniform"], "uniform"),
    **dict.fromkeys(["club_society", "club", "society", "clubs_societies", "kelab_persatuan", "kelab", "persatuan"], "club"),
    **dict.fromkeys(["sport_game", "sport", "sports", "game", "games", "sukan_permainan", "sukan", "permainan"], "sport"),
}


@router.get("/master/students")
def master_students(u: User = Depends(admin_only)):
    with get_db() as db:
        cat = lambda c: (f"(SELECT c.name FROM class_students m JOIN classes c ON c.id=m.class_id "  # noqa: E731
                         f"WHERE m.student_id=s.id AND c.category='{c}') AS {c}")
        return [dict(r) for r in db.execute(
            f"SELECT s.id, s.username AS student_no, s.name, s.class_name, s.qr_status, s.active, s.registered_at, "
            f"{', '.join(cat(c) for c in COCU)}, "
            f"EXISTS(SELECT 1 FROM photos p WHERE p.user_id=s.id) AS has_photo, "
            f"(SELECT COUNT(*) FROM achievements a WHERE a.student_id=s.id) AS achievements "
            f"FROM users s WHERE s.role='student' ORDER BY s.class_name, s.name")]


@router.post("/master/students/import")
def import_students(body: ImportIn, u: User = Depends(admin_only)):
    """CSV: student_no,name,class_id[,uniform_body,club_society,sport_game]. New students are added (not registered
    yet); existing ones get the new name, class ID and co-curricula (e.g. a new school year). A co-curriculum column
    that is missing from the file is left as it is; an empty cell removes that co-curriculum."""
    rows, have = read_csv(body.csv, STUDENT_ALIAS, {"no", "name", "cls"}, "student_no, name and class_id "
                          "(and optionally uniform_body, club_society, sport_game)")

    def apply(r):
        if not r.get("no") or not r.get("name") or not r.get("cls"):
            raise ValueError("student ID, name or class ID is empty")
        return upsert_student(db, check_id(r["no"], "student ID"), r["name"], r["cls"],
                              {c: r.get(c, "") for c in COCU if c in have})

    with get_db() as db:
        added, updated, problems = apply_rows(db, rows, apply)
        audit(db, u, "master.import", f"students: {len(rows)} rows",
              f"{added} added, {updated} updated, {len(problems)} skipped")
    return {"added": added, "updated": updated, "skipped": len(problems), "problems": problems[:20]}


# ------------------------------------------------------------------ master list: teachers
TEACHER_ALIAS = {
    **dict.fromkeys(["teacher_no", "teacher_id", "staff_id", "staff_no", "id", "no", "username"], "no"),
    **dict.fromkeys(["name", "full_name", "teacher_name", "nama"], "name"),
    **dict.fromkeys(["position", "post", "jawatan", "role", "title"], "position"),
    **dict.fromkeys(["email", "emel", "e_mail"], "email"),
    **dict.fromkeys(["co_curricula", "cocurricula", "co_curriculum", "cocurriculum", "in_charge", "in_charge_of",
                     "responsible_for", "kokurikulum"], "cocu"),
}


@router.get("/master/teachers")
def master_teachers(u: User = Depends(admin_only)):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT t.id, t.username AS teacher_no, t.name, t.position, t.email, t.qr_status, t.active, t.registered_at, "
            "EXISTS(SELECT 1 FROM photos p WHERE p.user_id=t.id) AS has_photo, "
            "(SELECT group_concat(c.name, ', ') FROM class_teachers ct JOIN classes c ON c.id=ct.class_id "
            " WHERE ct.teacher_id=t.id) AS classes "
            "FROM users t WHERE t.role='teacher' ORDER BY t.name")]


@router.post("/master/teachers/import")
def import_teachers(body: ImportIn, u: User = Depends(admin_only)):
    """CSV: teacher_id,name,position[,email,co_curricula]. co_curricula lists the co-curricula the teacher is in
    charge of, separated by ; or , (e.g. "Gadet Police; Basketball"). They must already be on the student master list.
    A teacher registers once with teacher ID and name, like a student."""
    rows, have = read_csv(body.csv, TEACHER_ALIAS, {"no", "name", "position"},
                          "teacher_id, name and position (and optionally email, co_curricula)")

    def apply(r):
        if not r.get("no") or not r.get("name"):
            raise ValueError("teacher ID or name is empty")
        cocu = [x.strip() for x in re.split(r"[;|,\n]", r.get("cocu", "")) if x.strip()] if "cocu" in have else None
        return upsert_teacher(db, check_id(r["no"], "teacher ID"), r["name"], r.get("position", ""), r.get("email", ""), cocu)

    with get_db() as db:
        added, updated, problems = apply_rows(db, rows, apply)
        audit(db, u, "master.import", f"teachers: {len(rows)} rows",
              f"{added} added, {updated} updated, {len(problems)} skipped")
    return {"added": added, "updated": updated, "skipped": len(problems), "problems": problems[:20]}


# ------------------------------------------------------------------ achievements (view only: teachers record them)
@router.get("/achievements")
def list_achievements(u: User = Depends(admin_only)):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT a.id, a.year, a.activity, a.level, a.award, s.username AS student_no, s.name, s.class_name, "
            "t.name AS added_by FROM achievements a JOIN users s ON s.id=a.student_id "
            "LEFT JOIN users t ON t.id=a.added_by ORDER BY a.year DESC, s.name, a.activity")]


# ------------------------------------------------------------------ backups
@router.get("/backups")
def backups(u: User = Depends(admin_only)):
    return {"dir": os.path.abspath(config.BACKUP_DIR), "copy_dir": config.BACKUP_COPY_DIR,
            "every_hours": config.BACKUP_HOURS, "keep": config.BACKUP_KEEP, "files": backup.list_backups()}


@router.post("/backups")
def backup_now(u: User = Depends(admin_only)):
    r = backup.backup_now("manual")
    with get_db() as db:
        audit(db, u, "backup.create", r["name"], "also copied to the second folder" if r["copied"] else r["copy_error"])
    return r


@router.get("/backups/{name}")
def download_backup(name: str, u: User = Depends(admin_only)):
    """Download one backup, e.g. to keep a copy on a USB drive. It holds every student's data: keep it safe."""
    p = backup.file_path(name)
    if not p:
        raise HTTPException(404, "Backup not found")
    with get_db() as db:
        audit(db, u, "backup.download", name)
    return FileResponse(p, media_type="application/octet-stream", filename=name)


# ------------------------------------------------------------------ activity log
@router.get("/audit")
def activity_log(q: str = "", before: int = 0, limit: int = Query(100, ge=1, le=500), u: User = Depends(admin_only)):
    """Newest first. q searches who, action, target and detail. before = the smallest id already shown."""
    sql, args = "SELECT * FROM audit_log WHERE 1=1", []
    if before:
        sql += " AND id < ?"
        args.append(before)
    for word in q.split()[:5]:
        sql += " AND (actor || ' ' || action || ' ' || target || ' ' || detail) LIKE ? ESCAPE '\\'"
        args.append("%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    with get_db() as db:
        return [dict(r) for r in db.execute(sql + " ORDER BY id DESC LIMIT ?", [*args, limit])]
