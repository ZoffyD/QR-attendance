"""Reports, activity log and backups."""
import os
from datetime import date, timedelta

from tests.conftest import class_id, make_teacher, qr_code, register, upload

TODAY = date.today()


def session(c, h, cid, day, title="Practice"):
    r = c.post("/api/sessions", headers=h, json={"title": title, "venue": "Dewan", "session_date": day.isoformat(),
                                                  "start_time": "14:00", "end_time": "16:00", "class_ids": [cid]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_reports(client, admin, teacher):
    a, b = register(client, "S001", "Aina", sport="Basketball"), register(client, "S002", "Bala", sport="Basketball")
    upload(client, "students", "student_no,name,class_id,sport_game\nX000,Placeholder Pupil,1A,Badminton\n")  # leaves Basketball
    cid = class_id(client, admin, "Basketball")
    s1 = session(client, teacher, cid, TODAY - timedelta(days=7))
    s2 = session(client, teacher, cid, TODAY)
    session(client, teacher, cid, TODAY + timedelta(days=7))      # planned: must not count yet
    qa, qb = qr_code(client, a), qr_code(client, b)
    for sid, code in [(s1, qa), (s2, qa), (s1, qb)]:
        assert client.post(f"/api/sessions/{sid}/scan", headers=teacher, json={"code": code}).json()["status"] == "checked_in"

    summary = client.get("/api/reports/classes", headers=teacher).json()
    assert summary["classes"] == [{**summary["classes"][0], "name": "Basketball", "students": 2, "sessions": 2, "present": 3,
                                   "possible": 4, "percent": 75.0}]
    assert summary["overall"] == {"sessions": 2, "present": 3, "possible": 4, "percent": 75.0, "below_75": 0}
    r = client.get(f"/api/reports/classes/{cid}", headers=teacher).json()
    by = {s["student_no"]: s for s in r["students"]}
    assert by["S001"]["percent"] == 100.0 and by["S002"]["percent"] == 50.0 and len(r["sessions"]) == 2
    day = (TODAY - timedelta(days=7)).isoformat()
    r = client.get(f"/api/reports/classes/{cid}?start={day}&end={day}", headers=teacher).json()
    assert [s["attended"] for s in r["students"]] == [1, 1] and r["percent"] == 100.0
    csv = client.get(f"/api/reports/classes/{cid}/export.csv", headers=teacher).text
    assert "S002,Bala" in csv and ",1,0,1,2,50.0" in csv
    # another teacher cannot see this co-curriculum; the admin sees the overall summary only
    _, other = make_teacher(client, "T002", "Zen", ["Badminton"])
    assert [c["name"] for c in client.get("/api/reports/classes", headers=other).json()["classes"]] == ["Badminton"]
    assert client.get(f"/api/reports/classes/{cid}", headers=other).status_code == 404
    overall = client.get("/api/reports/classes", headers=admin).json()
    assert {c["name"] for c in overall["classes"]} == {"Basketball", "Badminton"} and overall["overall"]["percent"] == 75.0
    assert client.get(f"/api/reports/classes/{cid}", headers=admin).status_code == 403
    assert client.get("/api/reports/classes", headers=a).status_code == 403


def test_activity_log(client, admin, teacher):
    register(client, "S001", "Aina", sport="Basketball")
    sid = client.get("/api/students", headers=teacher).json()[0]["id"]
    client.post(f"/api/students/{sid}/terminate", headers=teacher)
    upload(client, "students", "student_no,name,class_id\nS001,Aina,6B\n")
    log = client.get("/api/admin/audit", headers=admin).json()
    actions = [e["action"] for e in log]
    assert actions[:4] == ["master.import", "qr.terminate", "student.register", "master.import"]
    assert log[0]["detail"] == "0 added, 1 updated, 0 skipped" and log[1]["actor"] == "Eren (Teacher)"
    assert [e["action"] for e in client.get("/api/admin/audit?q=terminate", headers=admin).json()] == ["qr.terminate"]
    older = client.get(f"/api/admin/audit?before={log[1]['id']}", headers=admin).json()
    assert older[0]["id"] < log[1]["id"]
    assert client.get("/api/admin/audit", headers=teacher).status_code == 403


def test_backups(client, admin, teacher):
    register(client, "S001", "Aina")
    r = client.post("/api/admin/backups", headers=admin)
    assert r.status_code == 200 and os.path.exists(r.json()["path"])
    info = client.get("/api/admin/backups", headers=admin).json()
    assert r.json()["name"] in [f["name"] for f in info["files"]]
    d = client.get(f"/api/admin/backups/{r.json()['name']}", headers=admin)
    assert d.status_code == 200 and d.content[:15] == b"SQLite format 3"
    assert client.get("/api/admin/backups/..%2Ft.db", headers=admin).status_code == 404
    assert client.get("/api/admin/backups", headers=teacher).status_code == 403
    assert client.get("/api/admin/overview", headers=admin).json()["backup"]["last"]
