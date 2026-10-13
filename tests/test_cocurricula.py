"""The master list (students and teachers), achievements recorded by teachers, profile pictures, separate
portals, and upgrading an old database."""
import base64
import sqlite3
from datetime import date

from tests.conftest import class_id, login, make_teacher, qr_code, register, upload

MASTER = ("Student No,Name,Class ID,Uniform Body,Club / Society,Sport / Game\n"
          "13255,Vicky Tan,4E1,Gadet Police,Pancaragam Harmonica,Basketball\n"
          "13256,Aina Binti Ali,5S4,Puteri Islam,Pancaragam Harmonica,Bola Jaring\n"
          "13257,Bala Kumar,3E,Gadet Police,Kelab Robotik,Basketball\n")
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 200).decode()


def classes(c, h):
    return {x["name"]: x for x in c.get("/api/classes", headers=h).json()}


def test_student_list_creates_cocurricula_and_members(client, admin):
    assert upload(client, "students", MASTER)["added"] == 3
    cl = classes(client, admin)
    assert {n: cl[n]["category"] for n in cl} == {
        "Gadet Police": "uniform", "Puteri Islam": "uniform", "Pancaragam Harmonica": "club", "Kelab Robotik": "club",
        "Basketball": "sport", "Bola Jaring": "sport"}
    assert cl["Gadet Police"]["students"] == 2 and cl["Pancaragam Harmonica"]["students"] == 2
    ov = client.get("/api/admin/overview", headers=admin).json()["counts"]
    assert ov["students"] == 3 and ov["students_registered"] == 0 and ov["no_teacher"] == 6
    m = {s["student_no"]: s for s in client.get("/api/admin/master/students", headers=admin).json()}
    assert (m["13255"]["uniform"], m["13255"]["club"], m["13255"]["sport"]) == ("Gadet Police", "Pancaragam Harmonica", "Basketball")

    # new year: Vicky changes sport; a file without the club column leaves clubs alone; an empty cell removes
    r = upload(client, "students", "student_no,name,class_id,uniform_body,sport_game\n13255,Vicky Tan,5E1,,Badminton\n")
    assert r["updated"] == 1
    m = {s["student_no"]: s for s in client.get("/api/admin/master/students", headers=admin).json()}
    assert (m["13255"]["class_name"], m["13255"]["uniform"], m["13255"]["club"], m["13255"]["sport"]) == \
           ("5E1", None, "Pancaragam Harmonica", "Badminton")
    # the same name cannot be a club and a sport; that row is skipped and explained, the others still import
    r = upload(client, "students", "student_no,name,class_id,club_society\n13258,Chen Wei,2A,Basketball\n13259,Dina,2A,Kelab Catur\n")
    assert r["added"] == 1 and r["skipped"] == 1 and "line 2" in r["problems"][0] and "sport" in r["problems"][0]


def test_teacher_list_sets_who_is_in_charge(client, admin):
    upload(client, "students", MASTER)
    text = ("Teacher ID,Name,Jawatan,Email,Co-curricula\n"
            "T001,Eren Yeager,Senior Assistant,eren@school.edu,Gadet Police; Basketball\n"
            "T002,Zen,Music Teacher,,Pancaragam Harmonica\n"
            "T003,Mika,PE Teacher,,Netball\n"                      # not on the student list: refused
            "13255,Imposter,Teacher,,\n")                          # already a student ID
    r = upload(client, "teachers", text)
    assert (r["added"], r["skipped"]) == (2, 2)
    assert "Netball" in r["problems"][0] and "student" in r["problems"][1]
    cl = classes(client, admin)
    assert cl["Gadet Police"]["teachers"] == "Eren Yeager" and cl["Basketball"]["teachers"] == "Eren Yeager"
    t = {x["teacher_no"]: x for x in client.get("/api/admin/master/teachers", headers=admin).json()}
    assert t["T001"]["position"] == "Senior Assistant" and t["T001"]["email"] == "eren@school.edu" and t["T001"]["qr_status"] == "unregistered"
    # uploading again replaces the list of co-curricula; a file without that column leaves it alone
    upload(client, "teachers", "teacher_id,name,position,co_curricula\nT001,Eren Yeager,Senior Assistant,Basketball\n")
    assert classes(client, admin)["Gadet Police"]["teachers"] is None
    upload(client, "teachers", "teacher_id,name,position\nT001,Eren Yeager,Principal\n")
    t = {x["teacher_no"]: x for x in client.get("/api/admin/master/teachers", headers=admin).json()}
    assert t["T001"]["position"] == "Principal" and t["T001"]["classes"] == "Basketball"


def test_teacher_runs_a_cocurriculum_from_the_master_list(client, admin):
    upload(client, "students", MASTER)
    _, teacher = make_teacher(client, "T001", "Eren", ["Basketball"])
    cid = class_id(client, admin, "Basketball")
    detail = client.get(f"/api/classes/{cid}", headers=teacher).json()
    assert detail["category"] == "sport"
    assert {s["student_no"]: s["qr_status"] for s in detail["students"]} == {"13255": "unregistered", "13257": "unregistered"}
    # one student registers; the session counts the other as "not registered", not absent
    vicky = register(client, "13255", "Vicky Tan", on_list=False)
    s = client.post("/api/sessions", headers=teacher, json={"title": "Training", "venue": "Court", "class_ids": [cid],
                                                             "session_date": date.today().isoformat()}).json()["id"]
    d = client.get(f"/api/sessions/{s}", headers=teacher).json()
    assert (d["present"], d["absent"], d["unregistered"]) == (0, 1, 1)
    assert client.post(f"/api/sessions/{s}/scan", headers=teacher, json={"code": qr_code(client, vicky)}).json()["status"] == "checked_in"
    r = client.get(f"/api/reports/classes/{cid}", headers=teacher).json()
    assert r["percent"] == 100.0 and r["counted"] == 1 and r["unregistered"] == 1
    # the student's profile shows the three co-curricula with their teachers, and the attendance summary
    me = client.get("/api/student/me", headers=vicky).json()
    assert [(x["category"], x["name"]) for x in me["cocurricula"]] == [
        ("Uniform body", "Gadet Police"), ("Club / society", "Pancaragam Harmonica"), ("Sport / game", "Basketball")]
    assert me["cocurricula"][2]["teachers"] == "Eren"
    summary = {x["name"]: x for x in client.get("/api/student/attendance/summary", headers=vicky).json()}
    assert (summary["Basketball"]["held"], summary["Basketball"]["attended"], summary["Basketball"]["percent"]) == (1, 1, 100.0)
    assert summary["Gadet Police"]["percent"] is None


def test_achievements_recorded_by_teachers(client, admin):
    upload(client, "students", MASTER)
    _, eren = make_teacher(client, "T001", "Eren", ["Basketball"])
    _, zen = make_teacher(client, "T002", "Zen", ["Pancaragam Harmonica"])
    bb, ph = class_id(client, admin, "Basketball"), class_id(client, admin, "Pancaragam Harmonica")
    ids = {s["student_no"]: s["id"] for s in client.get("/api/admin/master/students", headers=admin).json()}
    add = lambda h, sid, cid, **kw: client.post("/api/achievements", headers=h, json={  # noqa: E731
        "student_id": sid, "class_id": cid, "year": 2025, "level": "daerah", "award": "Champion", **kw})
    assert add(eren, ids["13255"], bb).status_code == 200
    assert add(eren, ids["13255"], bb).status_code == 409                 # the same one twice
    assert add(eren, ids["13256"], bb).status_code == 404                 # Aina does not play basketball
    assert add(eren, ids["13256"], ph).status_code == 404                 # not Eren's co-curriculum
    assert add(zen, ids["13256"], ph, level="State", award="Gold").status_code == 200
    mine = client.get("/api/achievements", headers=eren).json()
    assert [(a["name"], a["activity"], a["level"], a["added_by"]) for a in mine] == [("Vicky Tan", "Basketball", "District", "Eren")]
    assert client.delete(f"/api/achievements/{mine[0]['id']}", headers=zen).status_code == 404   # not Zen's
    assert len(client.get("/api/admin/achievements", headers=admin).json()) == 2              # the admin sees all
    vicky = register(client, "13255", "Vicky Tan", on_list=False)
    assert [a["award"] for a in client.get("/api/student/me", headers=vicky).json()["achievements"]] == ["Champion"]
    assert client.delete(f"/api/achievements/{mine[0]['id']}", headers=eren).status_code == 200
    assert client.get("/api/student/me", headers=vicky).json()["achievements"] == []
    assert [e["action"] for e in client.get("/api/admin/audit?q=achievement", headers=admin).json()] == \
           ["achievement.remove", "achievement.add", "achievement.add"]


def test_profile_pictures(client, admin):
    upload(client, "students", MASTER)
    eid, eren = make_teacher(client, "T001", "Eren", ["Basketball"])
    _, zen = make_teacher(client, "T002", "Zen", ["Pancaragam Harmonica"])
    vicky = register(client, "13255", "Vicky Tan", on_list=False)
    bala = register(client, "13257", "Bala Kumar", on_list=False)
    assert client.post("/api/me/photo", headers=vicky, json={"data_url": JPEG}).status_code == 200
    vid = client.get("/api/me", headers=vicky).json()["id"]
    assert client.get("/api/me", headers=vicky).json()["has_photo"]
    assert client.get(f"/api/photos/{vid}", headers=vicky).content.startswith(b"\xff\xd8\xff")
    assert client.get(f"/api/photos/{vid}", headers=eren).status_code == 200      # Vicky plays basketball
    assert client.get(f"/api/photos/{vid}", headers=zen).status_code == 200       # and is in Pancaragam Harmonica
    assert client.get(f"/api/photos/{vid}", headers=admin).status_code == 200
    assert client.get(f"/api/photos/{vid}", headers=bala).status_code == 404      # another student
    _, mika = make_teacher(client, "T003", "Mika", ["Kelab Robotik"])
    assert client.get(f"/api/photos/{vid}", headers=mika).status_code == 404      # not Vicky's teacher
    # the scan result tells the teacher there is a photo to compare
    cid = class_id(client, admin, "Basketball")
    s = client.post("/api/sessions", headers=eren, json={"title": "T", "venue": "V", "session_date": "2026-10-13", "class_ids": [cid]}).json()["id"]
    assert client.post(f"/api/sessions/{s}/scan", headers=eren, json={"code": qr_code(client, vicky)}).json()["student"]["has_photo"]
    # only real pictures, and not too big
    for bad in ["data:image/gif;base64,R0lGODlh", "data:image/jpeg;base64," + base64.b64encode(b"not a jpeg").decode(),
                "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"0" * 420_000).decode()]:
        assert client.post("/api/me/photo", headers=eren, json={"data_url": bad}).status_code in (400, 422)
    assert client.post("/api/me/photo", headers=admin, json={"data_url": JPEG}).status_code == 403
    assert client.post("/api/me/photo", headers=eren, json={"data_url": JPEG}).status_code == 200
    assert client.get(f"/api/photos/{eid}", headers=zen).status_code == 404       # no shared co-curriculum
    client.delete("/api/me/photo", headers=vicky)
    assert client.get(f"/api/photos/{vid}", headers=vicky).status_code == 404


def test_separate_portal_addresses(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/student"
    for role in ("student", "teacher", "admin"):
        r = client.get(f"/{role}")
        assert r.status_code == 200 and "<form" in r.text


def test_upgrade_from_old_database(tmp_path, monkeypatch):
    """A database from an older version (separate master_students table, teacher sign-ups waiting for
    approval) is converted on start."""
    from app import config, db as dbm
    path = str(tmp_path / "old.db")
    monkeypatch.setattr(config, "DB_PATH", path)
    old = sqlite3.connect(path)
    old.executescript("""
      CREATE TABLE users (id INTEGER PRIMARY KEY, role TEXT NOT NULL, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', class_name TEXT NOT NULL DEFAULT '', pw_hash TEXT NOT NULL,
        approved INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1, qr_token TEXT UNIQUE,
        qr_status TEXT NOT NULL DEFAULT 'active', qr_printed_at TEXT, created_at TEXT NOT NULL);
      CREATE TABLE master_students (student_no TEXT PRIMARY KEY COLLATE NOCASE, name TEXT NOT NULL,
        class_name TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE TABLE classes (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, created_by INTEGER,
        created_at TEXT NOT NULL);
      CREATE TABLE achievements (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, year INTEGER NOT NULL,
        activity TEXT NOT NULL, level TEXT NOT NULL, award TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE (student_id, year, activity, level, award));
      INSERT INTO users(role,username,name,class_name,pw_hash,qr_token,created_at)
        VALUES ('student','S001','Aina','5S4','x$y','tok','2026-01-01T00:00:00Z');
      INSERT INTO users(role,username,name,email,pw_hash,approved,created_at)
        VALUES ('teacher','zen','Zen','zen@s.edu','x$y',0,'2026-01-01T00:00:00Z'),
               ('teacher','eren','Eren','eren@s.edu','x$y',1,'2026-01-01T00:00:00Z');
      INSERT INTO master_students VALUES ('S001','Aina Ali','5S4','2026-01-01'), ('S002','Bala','4E1','2026-01-01');
      INSERT INTO classes(name, created_at) VALUES ('Harmonika (A)', '2026-01-01');
      INSERT INTO achievements(student_id,year,activity,level,award,created_at) VALUES (1,2025,'Chess','School','Gold','x');
    """)
    old.commit()
    old.close()
    dbm.init_db()
    with dbm.get_db() as db:
        rows = {r["username"]: dict(r) for r in db.execute("SELECT * FROM users")}
        assert rows["S001"]["name"] == "Aina Ali" and rows["S001"]["qr_status"] == "active" and rows["S001"]["registered_at"]
        assert rows["S002"]["qr_status"] == "unregistered" and rows["S002"]["pw_hash"] == ""
        assert rows["eren"]["qr_status"] == "active" and rows["eren"]["position"] == ""
        assert rows["zen"]["qr_status"] == "unregistered" and rows["zen"]["approved"] == 1   # must register now
        assert db.execute("SELECT category FROM classes").fetchone()[0] == ""
        assert tuple(db.execute("SELECT class_id, added_by FROM achievements").fetchone()) == (None, None)
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='master_students'").fetchone()
