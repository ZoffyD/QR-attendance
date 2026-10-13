import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ.update({
    "ATT_DB_PATH": os.path.join(_tmp, "t.db"),
    "ATT_ADMIN_PASSWORD": "admin-secret",
    "ATT_SMTP_HOST": "",
})

from fastapi.testclient import TestClient  # noqa: E402

from app import config, ratelimit  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(config.DB_PATH + suffix):
            os.remove(config.DB_PATH + suffix)
    ratelimit.clear()
    with TestClient(app) as c:
        yield c


def login(c, username, password, role=None):
    r = c.post("/api/login", json={"username": username, "password": password, "role": role})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def admin(client):
    return login(client, "admin", "admin-secret")


def upload(c, kind, text):
    """The admin uploads the student or teacher master list (kind = 'students' | 'teachers')."""
    r = c.post(f"/api/admin/master/{kind}/import", headers=login(c, "admin", "admin-secret"), json={"csv": text})
    assert r.status_code == 200, r.text
    return r.json()


def add_master(c, no, name, cls, sport=""):
    """One student on the master list; sport puts them in that co-curriculum (Sport / game)."""
    upload(c, "students", f"student_no,name,class_id,sport_game\n{no},{name},{cls},{sport}\n")


def make_teacher(c, teacher_no, name=None, cocu=(), position="Teacher"):
    """A teacher on the teacher list (in charge of cocu), who then registers. Returns (id, headers)."""
    name = name or teacher_no.title()
    upload(c, "teachers", f"teacher_id,name,position,co_curricula\n{teacher_no},{name},{position},{'; '.join(cocu)}\n")
    r = c.post("/api/register/teacher", json={"teacher_no": teacher_no, "name": name,
                                              "email": f"{teacher_no.lower()}@school.edu", "password": "teach-pass"})
    assert r.status_code == 200, r.text
    h = {"Authorization": "Bearer " + r.json()["token"]}
    return c.get("/api/me", headers=h).json()["id"], h


def register(c, no, name, cls="5A", on_list=True, sport=""):
    if on_list:
        add_master(c, no, name, cls, sport)
    r = c.post("/api/register/student", json={"student_no": no, "name": name, "password": "student-pass"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def class_id(c, admin, name):
    return {x["name"]: x["id"] for x in c.get("/api/classes", headers=admin).json()}[name]


@pytest.fixture()
def teacher(client):
    """Eren (T001), in charge of Basketball. Members are added with register(..., sport='Basketball')."""
    add_master(client, "X000", "Placeholder Pupil", "1A", "Basketball")   # creates the co-curriculum
    return make_teacher(client, "T001", "Eren", ["Basketball"])[1]


def qr_code(c, headers):
    r = c.post("/api/student/qr", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["code"]
