import re

from tests.conftest import add_master, class_id, login, make_teacher, qr_code, register, upload

SESSION = {"title": "Practice", "venue": "Dewan", "session_date": "2026-10-13", "start_time": "14:00",
           "end_time": "16:00"}


def students(c, h):
    return {s["student_no"]: s for s in c.get("/api/students", headers=h).json()}


def new_session(c, h, ids, **kw):
    r = c.post("/api/sessions", headers=h, json={**SESSION, **kw, "class_ids": ids})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ------------------------------------------------------------------ logins and registration
def test_student_registers_once_and_logs_in(client):
    h = register(client, "S001", "Aina Ali", "5s4")
    me = client.get("/api/student/me", headers=h).json()
    assert me["student_no"] == "S001" and me["name"] == "Aina Ali" and me["class_name"] == "5S4"
    login(client, "s001", "student-pass", role="student")
    r = client.post("/api/register/student", json={"student_no": "S001", "name": "Aina Ali", "password": "other-pass"})
    assert r.status_code == 409 and "only once" in r.json()["detail"]


def test_teacher_registers_from_the_teacher_list(client, admin):
    add_master(client, "S001", "Aina", "5A", "Basketball")
    upload(client, "teachers", "teacher_id,name,position,co_curricula\nT001,Eren Yeager,Senior Assistant,Basketball\n")
    body = {"teacher_no": "T001", "name": "eren  YEAGER", "email": "eren@school.edu", "password": "teach-pass"}
    # not on the list, or wrong name: refused with the same message
    for no, name in [("T999", "Eren Yeager"), ("T001", "Someone Else")]:
        r = client.post("/api/register/teacher", json={**body, "teacher_no": no, "name": name})
        assert r.status_code == 400 and "teacher list" in r.json()["detail"]
    # before registering, the teacher cannot log in
    assert client.post("/api/login", json={"username": "T001", "password": ""}).status_code == 401
    assert client.post("/api/register/teacher", json=body).status_code == 200
    assert client.post("/api/register/teacher", json=body).status_code == 409   # only once
    h = login(client, "t001", "teach-pass", role="teacher")
    me = client.get("/api/teacher/me", headers=h).json()
    assert (me["teacher_no"], me["name"], me["position"], me["email"]) == ("T001", "Eren Yeager", "Senior Assistant", "eren@school.edu")
    assert [c["name"] for c in me["cocurricula"]] == ["Basketball"] and me["cocurricula"][0]["students"] == 1
    t = client.get("/api/admin/master/teachers", headers=admin).json()[0]
    assert t["qr_status"] == "active" and t["classes"] == "Basketball"


# ------------------------------------------------------------------ master list
CSV = "student_no,name,class_id\nS001,Aina Binti Ali,5S4\nS002,Bala Kumar,4e1\nS003,Chen Wei,3E\n,No Id,5S4\n"


def test_master_list_import_and_class_id(client, admin):
    r = client.post("/api/admin/master/students/import", headers=admin, json={"csv": "﻿" + CSV}).json()
    assert r == {"added": 3, "updated": 0, "skipped": 1, "problems": ["line 5: student ID, name or class ID is empty"]}
    for no, name in [("S999", "Aina Binti Ali"), ("S001", "Someone Else")]:
        r = client.post("/api/register/student", json={"student_no": no, "name": name, "password": "student-pass"})
        assert r.status_code == 400 and "master list" in r.json()["detail"]
    # name matching ignores case and extra spaces; name and class ID come from the list
    h = register(client, "s001", "aina  binti ALI", on_list=False)
    me = client.get("/api/student/me", headers=h).json()
    assert me == {**me, "student_no": "S001", "name": "Aina Binti Ali", "class_name": "5S4"}
    # new school year: re-upload moves the student to a new class; the account and QR stay
    r = client.post("/api/admin/master/students/import", headers=admin, json={"csv": "student_id,full_name,class\nS001,Aina Binti Ali,6S4\n"}).json()
    assert r["updated"] == 1
    assert client.get("/api/student/me", headers=h).json()["class_name"] == "6S4"
    lst = {m["student_no"]: m for m in client.get("/api/admin/master/students", headers=admin).json()}
    assert lst["S001"]["qr_status"] == "active" and lst["S002"]["qr_status"] == "unregistered"
    c = client.get("/api/admin/overview", headers=admin).json()["counts"]
    assert (c["students"], c["students_registered"]) == (3, 1)


def test_admin_only_uploads_and_views(client, admin):
    r = client.post("/api/admin/master/students/import", headers=admin, json={"csv": "id,name\nS1,A\n"})
    assert r.status_code == 400 and "class_id" in r.json()["detail"]
    add_master(client, "S010", "Dina", "2A")
    # adding, editing or removing single rows, achievements and teacher accounts are gone from the admin
    assert client.post("/api/admin/master", headers=admin, json={}).status_code in (404, 405)
    assert client.put("/api/admin/master/S010", headers=admin, json={}).status_code in (404, 405)
    assert client.delete("/api/admin/master/S010", headers=admin).status_code in (404, 405)
    assert client.post("/api/admin/achievements", headers=admin, json={}).status_code in (404, 405)
    assert client.post("/api/admin/teachers", headers=admin, json={}).status_code in (404, 405)
    # the day-to-day work is for teachers only
    assert client.post("/api/sessions", headers=admin, json={**SESSION, "class_ids": [1]}).status_code == 403
    assert client.get("/api/students", headers=admin).status_code == 403
    assert client.post("/api/achievements", headers=admin, json={}).status_code in (403, 422)


def test_students_cannot_change_class_id(client, teacher):
    h = register(client, "S001", "Aina", "5S4")
    assert client.patch("/api/student/me", headers=h, json={"class_name": "1A"}).status_code == 405
    assert client.get("/api/student/me", headers=h).json()["class_name"] == "5S4"


def test_each_role_uses_its_own_login(client, teacher):
    register(client, "S001", "Aina")
    r = client.post("/api/login", json={"username": "S001", "password": "student-pass", "role": "teacher"})
    assert r.status_code == 403 and "Student login" in r.json()["detail"]
    r = client.post("/api/login", json={"username": "T001", "password": "teach-pass", "role": "student"})
    assert r.status_code == 403


def test_roles_are_separated(client, admin, teacher):
    stu = register(client, "S001", "Aina")
    assert client.get("/api/admin/overview", headers=teacher).status_code == 403
    assert client.get("/api/students", headers=stu).status_code == 403
    assert client.get("/api/student/me", headers=teacher).status_code == 403
    assert client.get("/api/me").status_code == 401


# ------------------------------------------------------------------ QR: print once, terminate, register again
def test_qr_prints_only_once(client):
    h = register(client, "S001", "Aina")
    assert "<svg" in client.post("/api/student/qr", headers=h).json()["qr_svg"]
    r = client.post("/api/student/qr", headers=h)
    assert r.status_code == 409 and "already printed" in r.json()["detail"]
    assert client.get("/api/student/me", headers=h).json()["qr_printed_at"]


def test_terminate_qr_then_register_again(client, admin, teacher):
    aina = register(client, "S001", "Aina Ali", sport="Basketball")
    cid = class_id(client, admin, "Basketball")
    sess = new_session(client, teacher, [cid])
    old_code = qr_code(client, aina)
    assert client.post(f"/api/sessions/{sess}/scan", headers=teacher, json={"code": old_code}).json()["status"] == "checked_in"

    sid = students(client, teacher)["S001"]["id"]
    client.post(f"/api/students/{sid}/terminate", headers=teacher)
    assert client.get("/api/student/me", headers=aina).status_code == 401          # logged out at once
    r = client.post("/api/login", json={"username": "S001", "password": "student-pass"})
    assert r.status_code == 403 and "register again" in r.json()["detail"]
    sess2 = new_session(client, teacher, [cid], session_date="2026-10-20")
    assert client.post(f"/api/sessions/{sess2}/scan", headers=teacher, json={"code": old_code}).json()["status"] == "unknown"

    r = client.post("/api/register/student", json={"student_no": "S001", "name": "Someone Else", "password": "x-password"})
    assert r.status_code == 400
    aina2 = register(client, "S001", "aina  ali", on_list=False)
    new_code = qr_code(client, aina2)
    assert new_code != old_code
    assert client.post(f"/api/sessions/{sess2}/scan", headers=teacher, json={"code": new_code}).json()["status"] == "checked_in"
    assert len(client.get("/api/student/attendance", headers=aina2).json()) == 2     # history kept, still a member


# ------------------------------------------------------------------ sessions and scanning
def test_full_flow_scan_results(client, admin, teacher):
    aina, bala = register(client, "S001", "Aina", sport="Basketball"), register(client, "S002", "Bala", sport="Badminton")
    cid = class_id(client, admin, "Basketball")
    sid = new_session(client, teacher, [cid])
    a, b = qr_code(client, aina), qr_code(client, bala)
    scan = lambda code: client.post(f"/api/sessions/{sid}/scan", headers=teacher, json={"code": code}).json()  # noqa: E731
    r = scan(a)
    assert r["status"] == "checked_in" and r["student"]["has_photo"] is False
    assert scan(a)["status"] == "already"
    r = scan(b)   # Bala plays badminton: refused, nothing recorded
    assert r["status"] == "not_enrolled" and "not involved" in r["message"]
    assert client.get(f"/api/sessions/{sid}", headers=teacher).json()["present"] == 1
    assert scan("ATT1:garbage")["status"] == "unknown"
    hist = client.get("/api/student/attendance", headers=aina).json()
    assert hist[0]["venue"] == "Dewan" and hist[0]["start_time"] == "14:00" and hist[0]["classes"] == "Basketball"
    client.post(f"/api/sessions/{sid}/closed", headers=teacher, json={"closed": True})
    assert scan(a)["status"] == "closed"
    assert "Aina" in client.get(f"/api/sessions/{sid}/export.csv", headers=teacher).text


def test_joint_session_shared_by_teachers(client, admin):
    """Eren is in charge of Basketball and Badminton; Zen of Badminton only. Eren makes one joint session;
    both see it and scan into the same list. Mikasa, in charge of neither, does not see it."""
    for no, name, sport in [("S001", "Sam", "Basketball"), ("S002", "Jo", "Badminton"), ("S003", "Kim", "Bola Jaring")]:
        add_master(client, no, name, "5A", sport)
    _, eren = make_teacher(client, "T001", "Eren", ["Basketball", "Badminton"])
    _, zen = make_teacher(client, "T002", "Zen", ["Badminton"])
    _, mikasa = make_teacher(client, "T003", "Mikasa", ["Bola Jaring"])
    bb, bd = class_id(client, admin, "Basketball"), class_id(client, admin, "Badminton")
    sid = new_session(client, eren, [bb, bd])
    cal = lambda h: [s["id"] for s in client.get("/api/sessions?start=2026-10-01&end=2026-10-31", headers=h).json()]  # noqa: E731
    assert cal(eren) == [sid] and cal(zen) == [sid] and cal(mikasa) == []
    assert client.get(f"/api/sessions/{sid}", headers=mikasa).status_code == 404
    sam = register(client, "S001", "Sam", on_list=False)
    jo = register(client, "S002", "Jo", on_list=False)
    assert client.post(f"/api/sessions/{sid}/scan", headers=eren, json={"code": qr_code(client, sam)}).json()["status"] == "checked_in"
    assert client.post(f"/api/sessions/{sid}/scan", headers=zen, json={"code": qr_code(client, jo)}).json()["status"] == "checked_in"
    d = client.get(f"/api/sessions/{sid}", headers=zen).json()
    assert d["present"] == 2 and {r["scanned_by"] for r in d["rows"]} == {"Eren", "Zen"}


def test_split_class_is_one_session_with_a_venue_per_teacher(client, admin):
    """Pancaragam Harmonica is too big for one hall: Eren takes Hall A, Zen Hall B, at the same time.
    A second session at an overlapping time is refused (it would mark the other hall's students absent);
    both teachers scan into the one session, each recording their own venue."""
    for no, name in [("S001", "Sam"), ("S002", "Jo")]:
        add_master(client, no, name, "5A", "Basketball")
    _, eren = make_teacher(client, "T001", "Eren", ["Basketball"])
    _, zen = make_teacher(client, "T002", "Zen", ["Basketball"])
    bb = class_id(client, admin, "Basketball")
    sid = new_session(client, eren, [bb], venue="Hall A / Hall B")
    for start, end in [("15:00", "17:00"), ("13:00", "14:30"), ("", "")]:
        r = client.post("/api/sessions", headers=zen, json={**SESSION, "venue": "Hall B", "start_time": start, "end_time": end, "class_ids": [bb]})
        assert r.status_code == 409 and r.json()["detail"]["session_id"] == sid and "join that session" in r.json()["detail"]["message"]
    new_session(client, zen, [bb], start_time="16:00", end_time="18:00")        # right after: fine
    new_session(client, zen, [bb], session_date="2026-10-14")                   # another day: fine
    # editing a session onto an overlapping time is refused too; editing itself is not
    assert client.put(f"/api/sessions/{sid}", headers=eren, json={**SESSION, "venue": "Hall A / Hall B / Hall C", "class_ids": [bb]}).status_code == 200
    sam, jo = register(client, "S001", "Sam", on_list=False), register(client, "S002", "Jo", on_list=False)
    jo_code = qr_code(client, jo)
    r = client.post(f"/api/sessions/{sid}/scan", headers=eren, json={"code": qr_code(client, sam), "venue": "Hall A"}).json()
    assert r["status"] == "checked_in" and r["venue"] == "Hall A"
    assert client.post(f"/api/sessions/{sid}/scan", headers=zen, json={"code": jo_code, "venue": "Hall B"}).json()["venue"] == "Hall B"
    r = client.post(f"/api/sessions/{sid}/scan", headers=eren, json={"code": jo_code, "venue": "Hall A"}).json()
    assert r["status"] == "already" and r["venue"] == "Hall B" and r["scanned_by"] == "Zen"
    rows = {x["name"]: x for x in client.get(f"/api/sessions/{sid}", headers=zen).json()["rows"]}
    assert (rows["Sam"]["scan_venue"], rows["Jo"]["scan_venue"]) == ("Hall A", "Hall B")
    assert "Hall B" in client.get(f"/api/sessions/{sid}/export.csv", headers=zen).text
    assert client.get("/api/student/attendance", headers=jo).json()[0]["venue"] == "Hall B"


def test_teacher_only_sees_and_uses_own_cocurricula(client, admin):
    add_master(client, "S001", "Aina", "5A", "Basketball")
    add_master(client, "S002", "Bala", "5A", "Badminton")
    _, eren = make_teacher(client, "T001", "Eren", ["Basketball"])
    bb, bd = class_id(client, admin, "Basketball"), class_id(client, admin, "Badminton")
    assert [c["name"] for c in client.get("/api/classes", headers=eren).json()] == ["Basketball"]
    assert client.get(f"/api/classes/{bd}", headers=eren).status_code == 404
    # cannot create a session for someone else's co-curriculum, not even mixed with an own one
    assert client.post("/api/sessions", headers=eren, json={**SESSION, "class_ids": [bd]}).status_code == 403
    assert client.post("/api/sessions", headers=eren, json={**SESSION, "class_ids": [bb, bd]}).status_code == 403
    # members come only from the master list: there is no way to add or remove one
    assert client.post(f"/api/classes/{bb}/students", headers=eren, json={"student_no": "S002"}).status_code in (404, 405)
    assert client.post("/api/classes", headers=eren, json={"name": "My group"}).status_code in (404, 405)
    # the student list is only their own students
    assert set(students(client, eren)) == {"S001"}
    bala = [s for s in client.get("/api/admin/master/students", headers=admin).json() if s["student_no"] == "S002"][0]
    assert client.post(f"/api/students/{bala['id']}/terminate", headers=eren).status_code == 404


def test_undo_check_in(client, admin, teacher, monkeypatch):
    aina = register(client, "S001", "Aina", sport="Basketball")
    cid = class_id(client, admin, "Basketball")
    sid = new_session(client, teacher, [cid])
    code = qr_code(client, aina)   # shown once only: keep it for the second scan
    client.post(f"/api/sessions/{sid}/scan", headers=teacher, json={"code": code})
    row = [r for r in client.get(f"/api/sessions/{sid}", headers=teacher).json()["rows"] if r["name"] == "Aina"][0]
    assert row["can_undo"]
    assert client.delete(f"/api/sessions/{sid}/attendance/{row['student_id']}", headers=teacher).status_code == 200
    assert client.get(f"/api/sessions/{sid}", headers=teacher).json()["present"] == 0
    assert client.delete(f"/api/sessions/{sid}/attendance/{row['student_id']}", headers=teacher).status_code == 404
    # after the time limit it can no longer be undone
    client.post(f"/api/sessions/{sid}/scan", headers=teacher, json={"code": code})
    from app import routes_teacher
    monkeypatch.setattr(routes_teacher, "UNDO_MINUTES", -1)
    assert client.delete(f"/api/sessions/{sid}/attendance/{row['student_id']}", headers=teacher).status_code == 409
    actions = [e["action"] for e in client.get("/api/admin/audit?q=attendance", headers=admin).json()]
    assert actions == ["attendance.check_in", "attendance.undo", "attendance.check_in"]


def test_reschedule_session(client, admin, teacher):
    cid = class_id(client, admin, "Basketball")
    sid = new_session(client, teacher, [cid])
    r = client.put(f"/api/sessions/{sid}", headers=teacher,
                   json={**SESSION, "venue": "Hall 2", "session_date": "2026-11-02", "class_ids": [cid]})
    assert r.status_code == 200
    assert client.get(f"/api/sessions/{sid}", headers=teacher).json()["session"]["venue"] == "Hall 2"
    bad = client.put(f"/api/sessions/{sid}", headers=teacher,
                     json={**SESSION, "start_time": "16:00", "end_time": "15:00", "class_ids": [cid]})
    assert bad.status_code == 400


def test_admin_sees_everything(client, admin, teacher):
    register(client, "S001", "Aina", sport="Basketball")
    cid = class_id(client, admin, "Basketball")
    new_session(client, teacher, [cid])
    o = client.get("/api/admin/overview", headers=admin).json()["counts"]
    assert (o["teachers"], o["teachers_registered"], o["students_registered"], o["sessions"]) == (1, 1, 1, 1)
    d = client.get(f"/api/classes/{cid}", headers=admin).json()
    assert d["teachers"][0]["name"] == "Eren" and len(d["sessions"]) == 1


# ------------------------------------------------------------------ forgot password
def test_forgot_password_staff_gets_code(client, admin, teacher, capsys):
    for ident, user in [("t001@school.edu", "T001"), ("admin", "admin")]:
        assert client.post("/api/forgot-password", json={"identifier": ident}).status_code == 200
        code = re.search(r"reset code for .*: (\d{6})", capsys.readouterr().out).group(1)
        assert client.post("/api/reset-password", json={"identifier": user, "code": code,
                                                        "password": "reset-pass-1"}).status_code == 200
        login(client, user, "reset-pass-1")
        assert client.post("/api/reset-password", json={"identifier": user, "code": code,
                                                        "password": "again-pass-1"}).status_code == 400


def test_forgot_password_student_gets_code_from_teacher(client, teacher):
    register(client, "S001", "Aina", sport="Basketball")
    client.post("/api/forgot-password", json={"identifier": "S001"})
    s = students(client, teacher)["S001"]
    assert s["reset_requested"]
    code = client.post(f"/api/students/{s['id']}/reset-code", headers=teacher).json()["code"]
    assert client.post("/api/reset-password", json={"identifier": "S001", "code": code,
                                                    "password": "new-student-pw"}).status_code == 200
    login(client, "S001", "new-student-pw")
    assert not students(client, teacher)["S001"]["reset_requested"]


def test_wrong_codes_lock_the_code(client, teacher):
    register(client, "S001", "Aina", sport="Basketball")
    sid = students(client, teacher)["S001"]["id"]
    code = client.post(f"/api/students/{sid}/reset-code", headers=teacher).json()["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        client.post("/api/reset-password", json={"identifier": "S001", "code": wrong, "password": "whatever-1"})
    assert client.post("/api/reset-password", json={"identifier": "S001", "code": code,
                                                    "password": "whatever-1"}).status_code == 400


def test_change_password_and_logout(client, teacher):
    assert client.post("/api/me/password", headers=teacher,
                       json={"current_password": "wrong", "new_password": "new-pass-1"}).status_code == 400
    assert client.post("/api/me/password", headers=teacher,
                       json={"current_password": "teach-pass", "new_password": "new-pass-1"}).status_code == 200
    client.post("/api/logout", headers=teacher)
    assert client.get("/api/me", headers=teacher).status_code == 401
    login(client, "T001", "new-pass-1")


def test_pages_served(client):
    for page in ["/", "/student", "/teacher", "/admin", "/student/register", "/teacher/register", "/student/forgot",
                 "/teacher/forgot", "/admin/forgot", "/student/app", "/teacher/app", "/admin/app", "/static/app.js",
                 "/static/school/crest.svg"]:
        assert client.get(page).status_code == 200, page
    assert client.get("/admin/register").status_code == 404   # the admin cannot sign up
