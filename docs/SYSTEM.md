# QR Attendance: system documentation

Technical reference for whoever installs, maintains or extends the system. For everyday use see [USER_GUIDE.md](USER_GUIDE.md); for installation see [DEPLOYMENT.md](DEPLOYMENT.md).

**Contents**
1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Roles and permissions](#3-roles-and-permissions)
4. [Business rules](#4-business-rules)
5. [Data model](#5-data-model)
6. [Main flows](#6-main-flows)
7. [API reference](#7-api-reference)
8. [Security](#8-security)
9. [Configuration](#9-configuration)
10. [Front end](#10-front-end)
11. [Testing](#11-testing)
12. [Maintenance](#12-maintenance)
13. [Limitations and ideas](#13-limitations-and-ideas)
14. [Design choices](#14-design-choices)

---

## 1. Overview

A web application for taking attendance at school co-curricular activities with QR codes. The roles form a hierarchy:

- **Admin** uploads the school's master list, then only views.
  - **Student list:** every student with their class ID and three co-curricula (uniform body, club/society, sport/game).
  - **Teacher list:** every teacher with their position and the co-curricula they are in charge of.
  - **Views:** everything, an overall report, the activity log and backups.
- **Teachers** register once against the teacher list. Their profile shows their position and co-curricula. Everything they do is limited to those co-curricula:
  - scheduling sessions and scanning QR codes, with undo for 10 minutes;
  - recording achievements;
  - resetting student passwords and terminating lost QRs;
  - detailed reports.

  Several teachers in charge can scan into the same session from their own devices.
- **Students** register once against the student list, print their personal QR once, and have three pages: profile (with photo), attendance and achievements.

Each role has its own portal address (`/student`, `/teacher`, `/admin`). The system runs as one Python process with an SQLite file, in one Docker container.

## 2. Architecture

```
 Browser: /student  /teacher  /admin  (log-in pages)      /student/app  /teacher/app  /admin/app  (portals)
     │  HTTPS (from the host or Caddy) · JSON · Authorization: Bearer <token>
     ▼
 FastAPI app (uvicorn)  ── app/main.py             portal addresses, log in/out, teacher registration, photos,
     │                  │                          forgot/reset password
     │                  ├─ app/routes_admin.py     /api/admin/*   overview, master list uploads and views,
     │                  │                                         achievements view, backups, activity log
     │                  ├─ app/routes_teacher.py   /api/*         teacher profile, own students, co-curricula,
     │                  │                                         sessions, scan, undo, achievements
     │                  ├─ app/routes_reports.py   /api/reports/* attendance % (teacher detail, admin overall), CSV
     │                  ├─ app/routes_student.py   /api/student/* register, QR once, profile, attendance
     │                  ├─ backup.scheduler()      background task: backup every ATT_BACKUP_HOURS
     │                  └─ /static/*               CSS, JS and the pages
     ▼
 SQLite  data/attendance.db  (WAL mode, foreign keys on; photos stored inside)        data/backups/*.db
```

| Module | Responsibility |
|---|---|
| `app/config.py` | Reads settings from environment variables |
| `app/db.py` | Schema, upgrading older databases, connection (`get_db()` commits or rolls back), `now_iso()` |
| `app/security.py` | Password hashing, log-in tokens, reset codes, role dependencies (`admin_only`, `teacher_only`, `staff` for viewing, `student_only`) |
| `app/accounts.py` | Master list: `upsert_student()` and `set_cocu()` (one co-curriculum per category per student), `upsert_teacher()` (position, co-curricula in charge), achievement `LEVELS`, name normalisation |
| `app/ratelimit.py` | In-memory limits on guesses (per IP, and per IP + username for log-in) |
| `app/mailer.py` | Sends reset codes by SMTP, or prints them to the log |
| `app/util.py` | QR token generation, SVG QR rendering (segno), code parsing |
| `app/audit.py` | `audit(db, who, action, target, detail)`: one activity-log row in the same transaction as the change |
| `app/backup.py` | Online SQLite backups, pruning, the second-copy folder, the background scheduler |
| `app/static/` | `login`, `register`, `forgot` (shared by the portals; the portal comes from the address), `student`, `teacher`, `admin`; shared `app.js`, `style.css`; `school/crest.svg` (placeholder logo); `vendor/` (html5-qrcode, Inter font) |

**Tech stack:** Python 3.10+, FastAPI, Pydantic v2, Uvicorn, SQLite, segno, html5-qrcode 2.3.8; vanilla JavaScript (no build step). Licences are in [SOURCES.md](SOURCES.md).

## 3. Roles and permissions

| Action | Admin | Teacher | Student |
|---|:-:|:-:|:-:|
| Upload the student list and the teacher list | ✔ | | |
| View all students, teachers, co-curricula, achievements | ✔ | | |
| Overall report; activity log; backups | ✔ | | |
| Profile page with photo | | ✔ | ✔ |
| See students; terminate QR; issue student reset codes | | own students | |
| View a co-curriculum (teachers, members, sessions) | ✔ (all) | ✔ (own) | |
| Create, edit, close, delete, export sessions; scan; undo a check-in | | ✔ (own co-curricula) | |
| Record and remove achievements | | ✔ (own co-curricula) | |
| Calendar; detailed reports and register CSV | | ✔ (own) | |
| Register, print QR once, see own profile, attendance and achievements | | | ✔ |
| Change own password; forgot password | ✔ | ✔ | ✔ |

- **Own co-curricula:** a teacher's rows in `class_teachers`, set only by the teacher list upload.
- **Own students:** students who are members of any own co-curriculum.
- **Own sessions:** sessions with at least one own co-curriculum.

These rules are enforced in `own_class()`, `own_session()`, `own_student()` and `_check_classes()` in `routes_teacher.py`. Each portal is its own page (`student.html`, `teacher.html`, `admin.html`), and every endpoint checks the role again on the server.

## 4. Business rules

| # | Rule | Where |
|---|---|---|
| R1 | The master list **is** the set of student and teacher rows. Uploading creates everyone (`qr_status='unregistered'`, no password), so rosters and assignments exist before anyone registers. | `accounts.upsert_student`, `accounts.upsert_teacher` |
| R2 | Each student has at most one co-curriculum per category (`uniform`, `club`, `sport`). A co-curriculum is a `classes` row with that category, created the first time its name appears in the student list. A column missing from an upload leaves that category unchanged; an empty cell removes it. The same name cannot be in two categories. | `accounts.set_cocu` |
| R3 | Members of a co-curriculum come only from the student list. Teachers in charge come only from the teacher list; each name there must already be a co-curriculum, otherwise the row is refused. There is no endpoint to add or remove members or teachers by hand, or to create groups. | `accounts.upsert_teacher`, `routes_teacher` |
| R4 | A student or teacher can register only if the ID is on the list **and** the name matches (ignoring capital letters and extra spaces). The error does not say which part was wrong. | `routes_student.register`, `main.register_teacher`, `accounts.norm` |
| R5 | Everyone registers once. A student can register again only after their QR is terminated: it keeps the same record, co-curricula and attendance, with a new password and new QR. | `routes_student.register`, `main.register_teacher` |
| R6 | Name, class ID, position and co-curricula come from the master list. Nobody edits them in the portals; the admin uploads a corrected file. | `routes_admin` (uploads only) |
| R7 | The QR is shown only once (`qr_printed_at`). | `routes_student.get_qr_once` |
| R8 | Terminating a QR invalidates the token immediately, logs the student out, and blocks log-in until they register again. Only a teacher of the student may do it. | `routes_teacher.terminate_qr` |
| R9 | A teacher can only put their own co-curricula in a session (all of them must be own). | `routes_teacher._check_classes` |
| R9a | A co-curriculum cannot have two sessions whose times overlap on the same day (no time = the whole day), on create or edit; the 409 answer carries the existing `session_id` so the page can offer to join it. Reason: each session expects every member, so a second one would mark the other hall's students absent. A split class is one session (venue e.g. `Hall A / Hall B`). | `routes_teacher._check_overlap` |
| R9b | Each check-in stores the scanning teacher's venue (`attendance.venue`, "My venue"; the session's venue if none is given). It appears in the session list, the session CSV and the student's history. | `routes_teacher.scan` |
| R10 | A scan records attendance only when the student is a member of a co-curriculum of the session; otherwise nothing is written. One record per student per session, even with several teachers scanning at once (`UNIQUE` + `INSERT OR IGNORE`). Closed sessions refuse scans. | `routes_teacher.scan` |
| R11 | A check-in can be undone by a teacher of the session within `UNDO_MINUTES` (10) while the session is open. Check-ins and undos are written to the activity log. | `routes_teacher.undo_check_in` |
| R12 | Achievements are recorded by a teacher for a member of one of their own co-curricula; the activity is that co-curriculum. The same (year, activity, level, award) is stored once per student. A teacher can remove only achievements of their own co-curricula. | `routes_teacher.add_achievement` |
| R13 | Reset codes: 6 digits, stored hashed, valid `ATT_RESET_MINUTES`, one use, locked after 5 wrong tries. Staff receive them by email; students in person from one of their teachers. | `security.issue_reset_code`, `main.reset_password` |
| R14 | Reports count sessions dated up to today within the range, and current members. Unregistered students (no QR) are listed but left out of the percentages. Teachers get detail for their own co-curricula; the admin gets only the overall summary. | `routes_reports` |
| R15 | Photos: JPG, PNG or WebP only (checked by content), at most 400 KB (the page shrinks them to 360 px first). Visible to the owner, the admin, and teachers who share a co-curriculum with the person. | `main.upload_photo`, `main.get_photo` |
| R16 | Every change writes an activity-log row in the same transaction. Log-ins are not logged. | `audit.audit` |

## 5. Data model

```
                       users ─────────────────────────────────────────────────────────┐
                       ─────  role, username (student ID / teacher ID / admin), name, │ 1
                              email, class_name (class ID), position, qr_token,        │
                              qr_status (unregistered|active|terminated), qr_printed_at,
                              registered_at, active
          ┌──────────────┬────────────┬──────────────┬──────────────┬─────────┬───────┴──────┬─────────┐
          │ *            │ *          │ *            │ *            │ 1       │ *            │ *       │
   class_teachers   class_students   attendance   achievements    photos   auth_tokens   reset_codes
          │ *            │ *          │ *               │ * (class_id, added_by)
          └── classes ───┘          sessions ── session_classes ── classes
              (name, category:            (1)          (* : *)
               uniform|club|sport)
```

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Every account, and everyone on the master list | `role`; `username` (student ID, teacher ID or `admin`; unique, case-insensitive); `pw_hash` ('' until registered); `class_name` (students); `position` (teachers); `qr_status`; `qr_token`; `qr_printed_at`; `registered_at`; `active`; `approved` (kept from older versions, always 1) |
| `photos` | Profile pictures | `user_id` (one per person), `mime`, `data` (BLOB), `updated_at` |
| `classes` | Co-curricula | `name` unique; `category` `uniform`/`club`/`sport` (or `''` for a group made in an older version) |
| `class_teachers` | Teachers in charge (many to many), from the teacher list | |
| `class_students` | Members (many to many), from the student list | |
| `sessions` | One meeting | `title`, `venue`, `session_date`, `start_time`, `end_time`, `closed` |
| `session_classes` | Co-curricula taking part (joint sessions) | |
| `attendance` | Check-ins | `UNIQUE(session_id, student_id)`, `checked_in_at` UTC, `scanned_by`, `venue` (where the scanning teacher was) |
| `achievements` | Student achievements | `student_id`, `year`, `activity`, `level`, `award` (unique together); `class_id`, `added_by` |
| `auth_tokens` | Log-in sessions | `token_hash` (SHA-256 of the bearer token), `expires_at` |
| `reset_codes` | Forgot-password requests | one row per user; `code_hash` NULL until issued (students) |
| `audit_log` | Activity log | `at` UTC, `actor_id`, `actor` (name and role at the time), `action`, `target`, `detail` |

Times: `checked_in_at`, `created_at` etc. are UTC ISO strings; `session_date` and start/end times are local school time as entered.

**Upgrading:** `init_db()` brings older databases up to date. Tested in `test_upgrade_from_old_database`.
- Adds the missing columns: `classes.category`, `users.registered_at`, `users.position`, and `achievements.class_id` / `added_by`.
- Turns an old `master_students` table into student rows, then drops it.
- Turns teacher sign-ups that were never approved into teacher-list entries that still have to register.

## 6. Main flows

### 6.1 Master list upload
```
admin ──POST /api/admin/master/students/import {csv}──► for each row (in its own SAVEPOINT):
   upsert users row (role student; new → qr_status 'unregistered', pw_hash '')
   for each co-curriculum column in the file: set_cocu(student, category, name)
       → remove the student from classes of that category → find/create the class → add the student
admin ──POST /api/admin/master/teachers/import {csv}──► for each row:
   every name in co_curricula must be an existing co-curriculum, else the row is refused
   upsert users row (role teacher; new → 'unregistered'); replace the teacher's class_teachers rows
   a row that fails is rolled back and reported
◄── {added, updated, skipped, problems[]}
```

### 6.2 Registration (students and teachers)
```
POST /api/register/student {student_no, name, password}
POST /api/register/teacher {teacher_no, name, email, password}
   find users row of that role with that ID
   ├─ none, or norm(name) ≠ norm(row.name) → 400 "do not match the list"
   ├─ already registered                    → 409 "register only once"
   ├─ account disabled                      → 403
   └─ otherwise                             → set password (teachers: email), qr_status active,
                                              registered_at now (students: new qr_token)
◄── {token}  (logged in; the profile shows what the master list says)
```

### 6.3 Scan and undo
```
teacher device ──POST /api/sessions/{id}/scan {code}──► server  (teacher of the session only)
   code "ATT1:<token>" → find student with qr_token=<token>, qr_status=active, active=1
   ├─ session closed                                  → closed
   ├─ no such student                                 → unknown
   ├─ not a member of the session's co-curricula      → not_enrolled  (nothing written)
   ├─ INSERT OR IGNORE attendance → 0 rows            → already
   └─ inserted, activity log "attendance.check_in"    → checked_in (+ student.has_photo, undo_minutes)
DELETE /api/sessions/{id}/attendance/{student_id}     → within 10 min and session open: removed, logged
other teachers' devices poll GET /api/sessions/{id} every 5 s and see the change
```

### 6.4 Forgot password
```
POST /api/forgot-password {identifier}  → always the same generic answer
   teacher/admin: code generated, emailed (or printed to the log)
   student:       request row stored; shows in their teachers' My students list
                  teacher → POST /api/students/{id}/reset-code → code shown once to the teacher
POST /api/reset-password {identifier, code, password} → password set, all log-ins revoked
```

## 7. API reference

All endpoints take and return JSON. Authenticated endpoints need `Authorization: Bearer <token>` from `/api/login` or registration. Errors are `{"detail": "..."}` with a 4xx status. Interactive docs are at `/docs` while the server runs.

### Pages
| Path | Page |
|---|---|
| `/` | redirects to `/student` |
| `/student`, `/teacher`, `/admin` | log-in for that portal |
| `/student/register`, `/teacher/register` | registration |
| `/student/forgot`, `/teacher/forgot`, `/admin/forgot` | forgot password |
| `/student/app`, `/teacher/app`, `/admin/app` | the portals (a wrong role is sent to its own portal) |

### Public and account
| Method | Path | Body / query | Notes |
|---|---|---|---|
| POST | `/api/login` | `username, password, role` | → `{token, role, name}`; refuses another role's account |
| POST | `/api/logout` | | revokes the token |
| GET | `/api/me` | | current user, incl. `position`, `has_photo` |
| POST | `/api/me/password` | `current_password, new_password` | |
| POST / DELETE | `/api/me/photo` | `{data_url}` | students and teachers; rule R15 |
| GET | `/api/photos/{user_id}` | | the picture, if allowed (R15), else 404 |
| POST | `/api/register/student` | `student_no, name, password` | rules R4, R5 |
| POST | `/api/register/teacher` | `teacher_no, name, email, password` | rules R4, R5 |
| POST | `/api/forgot-password` | `identifier` | generic answer |
| POST | `/api/reset-password` | `identifier, code, password` | |
| GET | `/healthz` | | health check |

### Student (`student` role)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/student/me` | profile, `cocurricula` (3, with teachers), `achievements`, `has_photo`, QR printed time |
| POST | `/api/student/qr` | QR SVG and code; once only (409 after) |
| GET | `/api/student/attendance` | sessions attended with venue and times |
| GET | `/api/student/attendance/summary` | per co-curriculum: sessions held so far, attended, percent |

### Teacher (`teacher` role; everything limited to their own co-curricula)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/teacher/me` | teacher ID, name, position, email, `has_photo`, co-curricula in charge with counts |
| GET | `/api/students` | own students, with status, attendance count, reset requests |
| POST | `/api/students/{sid}/terminate` | rule R8 |
| POST | `/api/students/{sid}/reset-code` | → `{code}` to give in person |
| POST | `/api/sessions` | `title, venue, session_date, start_time, end_time, class_ids[]` (rule R9) |
| GET | `/api/sessions?start=YYYY-MM-DD&end=YYYY-MM-DD` | calendar |
| GET / PUT / DELETE | `/api/sessions/{sid}` | detail (`present`, `absent`, `unregistered`, rows with `can_undo`) / edit / delete |
| POST | `/api/sessions/{sid}/closed` | `{closed: bool}` |
| GET | `/api/sessions/{sid}/export.csv` | attendance as CSV |
| POST | `/api/sessions/{sid}/scan` | `{code, venue?}` → `{status, student?, time?, venue?, scanned_by?, message}` |
| DELETE | `/api/sessions/{sid}/attendance/{student_id}` | undo a check-in (rule R11) |
| GET / POST | `/api/achievements` | list for own co-curricula / record `{student_id, class_id, year, level, award}` |
| DELETE | `/api/achievements/{id}` | own co-curricula only |
| GET | `/api/reports/classes/{cid}?start=&end=` | sessions and students (`registered`, attended, percent, last_seen) |
| GET | `/api/reports/classes/{cid}/export.csv?start=&end=` | register: one column per session, 1/0, totals |

### Teacher and admin (`staff`, viewing)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/classes` | teacher: own co-curricula; admin: all |
| GET | `/api/classes/{cid}` | category, teachers (with position), members with status, sessions |
| GET | `/api/reports/classes?start=&end=` | summary per co-curriculum plus `overall` (sessions, present, possible, percent, below_75) |

### Admin (`admin` role, prefix `/api/admin`)
| Method | Path | Notes |
|---|---|---|
| GET | `/overview` | counts (students and teachers, registered; co-curricula without a teacher; sessions; check-ins; achievements), last backup |
| GET | `/master/students` | students with class ID, `uniform`, `club`, `sport`, status |
| POST | `/master/students/import` | `{csv}`: `student_no,name,class_id[,uniform_body,club_society,sport_game]` (common aliases and Malay names accepted) → `{added, updated, skipped, problems}` |
| GET | `/master/teachers` | teachers with position, email, co-curricula, status |
| POST | `/master/teachers/import` | `{csv}`: `teacher_id,name,position[,email,co_curricula]` (co-curricula separated by `;`) → `{added, updated, skipped, problems}` |
| GET | `/achievements` | all achievements with the student and who recorded them |
| GET / POST | `/backups` | folder, schedule and files / back up now |
| GET | `/backups/{name}` | download one backup file |
| GET | `/audit?q=&before=&limit=` | activity log, newest first; `before` = smallest id already shown (paging) |

## 8. Security

| Threat | Protection |
|---|---|
| Stolen database | Passwords hashed with scrypt; log-in tokens and reset codes stored only as hashes |
| Password guessing | Rate limits: log-in 10 failures / 10 min per IP + username; registration 10 / 15 min per IP; forgot 10 / 15 min; reset 20 / 15 min; reset code locked after 5 wrong tries |
| All visitors sharing one rate limit behind a cloud proxy | The container trusts `X-Forwarded-For` (`--proxy-headers`, `FORWARDED_ALLOW_IPS`), so each visitor is counted separately |
| Someone registering as another person | Must know both the ID and the exact name from the master list; the error does not reveal which was wrong |
| Logging in before registering | Unregistered rows have no password hash, so no password can match |
| A teacher recording the wrong student | Sessions only for own co-curricula; rosters only from the master list; outsiders refused with nothing written; photo shown on every scan; 10-minute undo; every check-in in the activity log |
| A teacher seeing other co-curricula | Students, sessions, reports, achievements and photos are filtered to own co-curricula on the server |
| Friend scanning for an absent student | QR printed once only; one account per student ID; photo check at the scan; terminate + re-register for lost QRs |
| Forged QR | QR holds a long random token (no personal data); unknown tokens are rejected |
| Harmful file uploaded as a photo | Only JPG/PNG/WebP, checked by the file's first bytes; at most 400 KB; served with its image type and `nosniff` |
| Finding out who has an account | Forgot-password answer is the same whether or not the account exists |
| Wrong role | Every endpoint checks the role; separate portal addresses |
| Cross-site scripting | Pages build the DOM with `textContent`, never by inserting user text as HTML |
| Eavesdropping | HTTPS from the cloud host or Caddy (see [DEPLOYMENT.md](DEPLOYMENT.md)) |
| Lost data, or changes nobody can explain | Automatic backups; activity log |
| Downloading arbitrary files via the backup endpoint | Only names matching `attendance-YYYYMMDD-HHMMSS-kind.db` inside the backup folder are served |
| Container compromise | Runs as an unprivileged user (`att`); the entrypoint only uses root to give `/data` to that user |

Tokens live in the browser's `sessionStorage` (cleared when the tab closes) and expire after `ATT_LOGIN_HOURS`. More in [PRIVACY.md](PRIVACY.md).

## 9. Configuration

Environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `ATT_ADMIN_PASSWORD` | (none) | Password for the `admin` account, used only when it is first created (random and printed in the log if empty) |
| `ATT_ADMIN_EMAIL` | | Where the admin's reset codes go |
| `ATT_DB_PATH` | `data/attendance.db` (`/data/attendance.db` in Docker) | Database file |
| `ATT_LOGIN_HOURS` | 12 | How long a log-in lasts |
| `ATT_RESET_MINUTES` | 30 | How long a reset code works |
| `ATT_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_FROM`, `_SSL` | | Email for staff reset codes; without a host, codes are printed in the log |
| `ATT_BACKUP_HOURS` | 24 | Automatic backup interval in hours; 0 turns it off |
| `ATT_BACKUP_KEEP` | 30 | Newest backups kept |
| `ATT_BACKUP_DIR` | next to the database, `backups/` | Backup folder |
| `ATT_BACKUP_COPY_DIR` | | Optional second folder for every backup |
| `PORT` | 8000 | Port inside the container (set by most cloud hosts) |
| `FORWARDED_ALLOW_IPS` | `*` in the image | Proxies whose `X-Forwarded-For` is trusted |
| `TZ` | | Server time zone, e.g. `Asia/Kuala_Lumpur` |

The school's name, motto and logo are set in `SCHOOL` at the top of `app/static/app.js` (see the README).

## 10. Front end

- Plain HTML, CSS and JavaScript with no build step. `app.js` has the shared parts:
  - `PORTAL` (taken from the address), `HOME` and `SCHOOL`
  - `api()`: fetch with the token, which turns errors into readable messages
  - `h()`: a small DOM builder
  - `requireRole()` + `setupHeader()`: sends a wrong role to its own portal and fills the header (photo, name, **Change password** dialog, **Log out**)
  - `avatar()` and `choosePhoto()`: pictures are fetched with the token and shown from blob URLs; uploads are cropped to a square and shrunk to 360 px in the browser
  - `calendar()`, `studentList()`, `tabBar()`, `catPill()`, `levelPill()`, `bar()`
- Each portal is one page with hash routes:
  - **`student.html`:** `#profile`, `#attendance`, `#achievements`
  - **`teacher.html`:** `#profile`, `#calendar`, `#students`, `#achievements`, `#reports`, `#class/{id}`, `#session/{id}`, `#new?date=&class=`, `#edit/{id}`
  - **`admin.html`:** `#overview`, `#master/students`, `#master/teachers`, `#classes`, `#class/{id}`, `#achievements`, `#reports`, `#log`
- **`style.css`** is a white-and-blue design with colour tokens on `:root`. Each portal has its own shade of blue under `html[data-role=student|teacher|admin]`. All text colours are at least 4.5:1 against white (WCAG AA). Cards have rounded corners, labels are small capitals, and the Inter font is bundled in `static/vendor/inter`. Percentage bars fill in when they come into view; with *reduce motion*, nothing moves. The pages work on phones.
- The camera scanner uses html5-qrcode, which browsers only allow on `https://` or `localhost`. A USB scanner works anywhere, because it types the code into the scan box followed by Enter.

## 11. Testing

```
pip install -r requirements-dev.txt
python -m pytest -q
```
| File | Covers |
|---|---|
| `tests/test_flow.py` | Student upload and class ID; admin only uploads and views; student and teacher registration (once, name match); QR once; terminate and register again; role separation; teachers limited to own co-curricula (sessions, students, rosters); joint sessions shared between teachers; all scan results; undo within the time limit; forgot password; change password; page addresses |
| `tests/test_cocurricula.py` | Co-curricula created from the student list, category changes and conflicts; teacher list (assignments, unknown names refused, re-upload replaces); "not registered" in sessions and reports; student profile and attendance summary; achievements by teachers (own co-curricula and members only); profile pictures (who may see them, file checks); portal addresses; upgrading an old database |
| `tests/test_extras.py` | Reports (planned sessions not counted, date ranges, CSV, own co-curricula only, admin overall only), activity log (search, paging), backups (safe download) |

`tests/conftest.py` gives each test an empty temporary database. Rate limits are not covered by automated tests. GitHub Actions (`.github/workflows/ci.yml`) runs the tests and builds the Docker image on every push.

## 12. Maintenance

| Task | How |
|---|---|
| Back up | Automatic (see `ATT_BACKUP_*`). Manual: admin **Overview → Backups → Back up now / Download**, or `scripts/backup.sh` with Docker Compose |
| Restore | Stop the app, copy a backup over the database file, delete `-wal`/`-shm` files, start again |
| Start over | Stop the app, delete the database file (and `-wal`/`-shm` files) |
| Forgot the admin password | Without SMTP or `ATT_ADMIN_EMAIL`, use *Forgot password?* at `/admin` with username `admin`: the code appears in the server log (`docker compose logs app`, or the host's log page) |
| New school year | Admin uploads the new student list, then the teacher list; accounts, QR codes and attendance stay |
| Upgrade | Replace the code (or redeploy), keep the data folder or volume, restart. Older databases are upgraded automatically |

## 13. Limitations and ideas

- **One server process.** The rate limiter and the backup scheduler live in memory, so run a single Uvicorn worker (the default). That is plenty for one school.
- **Reports use current members.** A student who changed co-curriculum mid-year is counted against every session in the range; narrow the date range for them.
- **After the undo window, a wrong check-in stays.** Nobody can edit attendance later; the activity log shows who scanned it. An idea: an admin-approved correction request.
- **Nobody can block or remove an account in the portals.** The admin only views, and uploading a list without someone does not delete them (their history stays). An idea: an *active* column in the CSV, so a student who left can be switched off by upload.
- **A student with no teacher** (their co-curricula have no teacher in charge) cannot get a password reset code until the teacher list covers them.
- **Photos are not checked by a person.** A student could upload a picture of someone else; the teacher sees the mismatch at the scan.
- **No camera on plain-HTTP school networks.** Use a host with HTTPS, Caddy with a domain, or USB scanners.

## 14. Design choices

- **Python (FastAPI) + vanilla JavaScript, not a single-page framework such as Angular or React.** The front end is small: a few pages with tables and forms. Without a build step, the whole system is one Docker image that anyone can run or read. A framework would only change the pages; the API in section 7 would stay the same, so the pages could be rebuilt in one later.
- **SQLite, not a database server.** One school, a few hundred students and a few teachers scanning at once fit easily: WAL mode lets several readers and one writer work together, and `UNIQUE` + `INSERT OR IGNORE` makes simultaneous scans safe. Backing up is copying one file, photos included.
- **The master list as user rows.** Rosters and teacher assignments exist from day one, and registering only adds a password (and a QR). There is no second copy of the lists to keep in step.
- **Admin uploads, teachers act.** The admin's job is the school's records; the day-to-day work and its accountability sit with the teacher in charge. Assigning teachers through the uploaded list, rather than by clicks in the portal, means the list in the school office and the system can't drift apart.
