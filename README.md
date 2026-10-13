# QR Attendance

Attendance for school co-curricular activities with QR codes. A prototype that shows how one scan can replace paper attendance lists.

- The admin uploads the school's **master list**: a **student list** (class ID and the three co-curricula: uniform body, club/society, sport/game) and a **teacher list** (position and the co-curricula each teacher is in charge of).
- Students and teachers **register once**. Each student prints their own QR code, **once**.
- Teachers **scan** the QR codes at each session, for **their own co-curricula only**. Anyone else is refused and nothing is recorded.
- Students see their profile, their attendance and their achievements.

Python (FastAPI) + SQLite in one small Docker container. No external services are needed.

## Three separate portals

| Address | Who | Main features |
|---|---|---|
| `/student` (also `/`) | Students | **Profile** (photo, student ID, name, class ID, three co-curricula, QR printed once), **Attendance**, **Achievements** |
| `/teacher` | Teachers | **Profile** (photo, teacher ID, name, position, co-curricula in charge), calendar, sessions and scanning, my students, achievements, reports: all limited to their own co-curricula |
| `/admin` | Main administrator | Overview, **Master list → Students / Teachers** (upload and view), co-curricula, achievements, overall report, activity log, backups. View only, apart from the two uploads |

Each portal has its own log-in and forgot password. Students and teachers register once against the master list. **Change password** and **Log out** sit at the top of every page.

### Admin: uploads, then views
- **Student list:** `student_no,name,class_id,uniform_body,club_society,sport_game` (sample: [scripts/sample_students.csv](scripts/sample_students.csv)). Co-curricula are created with their members.
- **Teacher list:** `teacher_id,name,position,email,co_curricula` (sample: [scripts/sample_teachers.csv](scripts/sample_teachers.csv)). `co_curricula` lists the co-curricula a teacher is in charge of, separated by `;`. This is the only way a teacher is put in charge.
- Views every student, teacher, co-curriculum and achievement, an **overall** attendance report, the **activity log** and **backups**. The admin does not edit single rows: fix the spreadsheet and upload it again.

### Teacher: only their own co-curricula
- A **profile page** like the student's: teacher ID, name, position, photo, and the co-curricula they run, each with **+ New session**.
- **Sessions** can only include the teacher's own co-curricula, so the wrong one can't be picked.
- **Scan:**
  - **Check-in successful**, with the student's photo to compare;
  - **Student is not involved in this session**: nothing recorded;
  - **Already checked in**.

  A wrong check-in can be **undone within 10 minutes**. Every check-in and undo is in the activity log.
- **My students** (own co-curricula only): *Terminate QR* (lost QR) and *Reset code* (forgotten password).
- **Achievements:** record them for members of their own co-curricula.
- **Reports:** student-by-student detail for their own co-curricula only, and a register CSV for Excel.

### Student: three pages
- **Profile:** photo (uploaded by the student), student ID, name, class ID, the three co-curricula with their teachers, and the QR (printed **once**).
- **Attendance:** percentage per co-curriculum, and every session attended with venue and time.
- **Achievements:** year, activity, level and award.

**Forgot password** works for every role:
- **Teachers and the admin:** the 6-digit code is emailed, or printed in the server log when email is not set up.
- **Students:** they get the code from their co-curriculum teacher.

## Try it

**Windows, no Docker** (Python 3.10+):
```
pip install -r requirements.txt
scripts\start-windows.bat
```
The first start asks you to choose the admin password. Then:
1. Open http://localhost:8000/admin and log in as `admin`.
2. Go to **Master list**:
   - **Students:** upload `scripts/sample_students.csv`.
   - **Teachers:** upload `scripts/sample_teachers.csv`.
3. Register a teacher at http://localhost:8000/teacher → *First time? Register*: `T001`, `Eren Yeager`.
4. Register a student at http://localhost:8000/student → *First time? Register*: `13255`, `Vicky Tan`.

**Docker:**
```bash
cp .env.example .env     # set ATT_ADMIN_PASSWORD
docker compose up -d --build
```

## Put it online (from GitHub)

GitHub stores the code. GitHub Pages can't run it, because it needs a server and a database. Connect the GitHub repository to a host that runs Docker containers, such as **Render**, **Railway** or **Fly.io**. They build the `Dockerfile` and give you an `https://` address, so the camera works on phones.

Two settings matter:
1. Set the environment variable `ATT_ADMIN_PASSWORD`.
2. Attach a **persistent volume at `/data`**. Without it, the database is wiped whenever the app restarts or redeploys.

Step by step: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Browsers allow the camera only on `https://` addresses (or `localhost`). Without HTTPS, use a USB QR scanner: click the scan box and scan.

## Documentation

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md): step-by-step guide for the admin, teachers and students
- [docs/SYSTEM.md](docs/SYSTEM.md): architecture, business rules, data model, API, security, testing
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): online with Docker, school network, backups, email
- [docs/PRIVACY.md](docs/PRIVACY.md): what is stored (including photos) and how it is protected
- [docs/SOURCES.md](docs/SOURCES.md): every source used (libraries, font, design reference) and licences
- [docs/DEVELOPMENT_LOG.md](docs/DEVELOPMENT_LOG.md): what was built, in what order and why, bugs fixed, how it was tested

## Design

Clean **white and blue** pages with one blue accent. Each portal has its own shade: bright blue for students, ocean blue for teachers, navy for the admin. All text meets WCAG AA contrast (at least 4.5:1). The log-in pages are a single card on the school's crest and name.

**School name and logo:** the system ships with a made-up school, *SMK Taman Harmoni*. To use the real one:
1. Change `SCHOOL` near the top of `app/static/app.js` (name, short name, motto).
2. Replace `app/static/school/crest.svg` with the real logo. A PNG works too; change `logo` in `SCHOOL` to point to it.

## Develop

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
GitHub Actions runs the tests and builds the Docker image on every push (`.github/workflows/ci.yml`).

## Project layout

| Path | What it does |
|---|---|
| `app/main.py` | Start-up, portal addresses, log in/out, teacher registration, profile photos, forgot password |
| `app/routes_admin.py` | Admin: overview, master list uploads (students, teachers) and views, achievements view, backups, activity log |
| `app/routes_teacher.py` | Teachers: profile, own students, co-curricula, sessions, calendar, scanning, undo, achievements |
| `app/routes_reports.py` | Attendance reports (teacher detail, admin overall) and register CSV |
| `app/routes_student.py` | Students: register once, QR once, profile, attendance |
| `app/accounts.py` | Master list: students, teachers and their co-curricula |
| `app/backup.py`, `app/audit.py` | Automatic backups, activity log |
| `app/db.py` | Database tables (and upgrading older databases) |
| `app/static/` | Pages: `login`, `register`, `forgot`, `student`, `teacher`, `admin`; `school/crest.svg` (placeholder logo) |
| `scripts/` | Windows start script, Docker entrypoint, backup/restore, sample CSV files |
