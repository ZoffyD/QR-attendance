# Development log

What was built, in what order, and why. Each stage followed a request from the project owner and was checked with automated tests and a browser test before moving on. Sources of everything used are in [SOURCES.md](SOURCES.md); how the finished system works is in [SYSTEM.md](SYSTEM.md).

**Contents**
1. [Starting point: students could not register or log in](#1-starting-point)
2. [First rebuild: a simpler system](#2-first-rebuild)
3. [Admin password and clean-up](#3-admin-password-and-clean-up)
4. [Own log-ins, shared classes, calendar, one-time QR](#4-own-log-ins-shared-classes-calendar-one-time-qr)
5. [Class ID from the school's master list](#5-class-id-from-the-master-list)
6. [Fix: editing the master list made duplicates](#6-fix-editing-the-master-list-made-duplicates)
7. [First redesign and documentation](#7-first-redesign-and-documentation)
8. [Backups, reports, activity log (and HTTPS, later removed)](#8-backups-reports-activity-log)
9. [Co-curricula and achievements in the master list; separate portals; ready for GitHub](#9-co-curricula-achievements-separate-portals)
10. [Cinematic design](#10-cinematic-design), then a [readability pass](#readability-pass-after-feedback) and simpler log-in pages
11. [Hierarchy, profiles and white-and-blue](#11-hierarchy-profiles-and-white-and-blue)
12. [Bugs found and fixed along the way](#12-bugs-found-and-fixed)
13. [How everything was tested](#13-how-everything-was-tested)
14. [Key decisions](#14-key-decisions)

---

## 1. Starting point
The earlier version did not let students register or log in. Rather than patch it, the owner asked for a simpler system with clear roles:
- the admin manages teachers and oversees everything;
- teachers make classes and sessions, and scan;
- students register themselves, print their QR, and see what they attended;
- forgot password works for everyone.

## 2. First rebuild
- **Server:** Python with FastAPI, one SQLite database file (`app/db.py`), started with Uvicorn.
- **Accounts:** one `users` table with a role (admin, teacher, student).
  - Passwords are hashed with scrypt (`app/security.py`).
  - A log-in creates a random token. Only its hash is stored, and the browser keeps the token in `sessionStorage`.
- **Admin:**
  - the first start creates the `admin` account from `ATT_ADMIN_PASSWORD`;
  - the admin registers teachers and sees an overview.
- **Teacher:**
  - creates classes and adds students;
  - creates sessions with venue and time;
  - scans QR codes, with the camera (html5-qrcode) or a USB scanner.
- **Scan results:** *Check-in successful*, *Student is not involved in this session*, *Already checked in*.
- **Student:** registers and gets a QR containing a long random token (`ATT1:<token>`, no personal data). They see their attended sessions with time and venue.
- **Forgot password:** a 6-digit code that works once, for 30 minutes, with at most 5 tries.
- **Tests:** written with pytest (`tests/`).

## 3. Admin password and clean-up
- **Admin password:** set with `ATT_ADMIN_PASSWORD` on the first start, then changed in the app under *Change my password*.
- **Clean-up:** unused files and the old version were removed. `scripts/start-windows.bat` was written: it asks for the admin password on the first start.

## 4. Own log-ins, shared classes, calendar, one-time QR
- **Separate log-ins per role**; a teacher's own sign-up waits for the admin's approval.
- **Shared classes:** several teachers can be in charge of one class (`class_teachers`), e.g. *Pancaragam Harmonika (A)* for seniors and *(B)* for juniors.
- **Joint sessions:** one session for several classes (`session_classes`). Every teacher in charge sees it and scans from their own laptop or phone into **the same list**.
  - `UNIQUE(session_id, student_id)` with `INSERT OR IGNORE` means two teachers scanning at the same moment never double-count.
  - The list refreshes every 5 seconds.
- **Calendar:** a month view of each teacher's sessions with time and venue; click a day to plan a session.
- **Register once:** a second registration is refused unless a teacher has **terminated** the student's QR (for a lost card). Then the student registers again and keeps their history.
- **QR printed once:** `qr_printed_at` is stored; after the first time, the QR cannot be shown again, so students can't print copies for friends.
- **Student profile:** student ID, name and class ID.
- **Forgot password by role:**
  - **Teachers and admin:** the code is emailed (or printed in the server window without email).
  - **Students:** the request appears on the teachers' list, and a teacher gives the code in person.

## 5. Class ID from the master list
The owner pointed out that the class ID must not be typed by students: it comes from the school's records.
- A **master list** CSV (`student_no,name,class_id`) is imported by the admin.
- Registration only works when the student ID **and** the name match the master list, ignoring capital letters and extra spaces. The error doesn't say which part was wrong.
- Students and teachers can no longer edit the class ID.

## 6. Fix: editing the master list made duplicates
**Cause:** *Edit* only filled in the form, and *Save* saved by the student ID in the form. Changing the ID therefore created a new entry.

**Fix:**
- Editing now targets the original entry (`PUT /api/admin/master/{old id}`), even when the ID changes; the student's account follows.
- *Add* refuses an ID that already exists.

## 7. First redesign and documentation
- A cleaner light design with a gradient header, cards, pill tabs and dark mode, which was replaced later (section 10).
- **Calendar bug fixed:** the last day of some months was missing (see section 11).
- **Documentation written:** `USER_GUIDE.md` for the admin, teachers and students, and `SYSTEM.md` for maintainers.

## 8. Backups, reports, activity log
The owner chose these improvements from a list of recommendations:
- **Automatic backups** (`app/backup.py`):
  - every 24 hours, SQLite's online backup copies the database while it is in use;
  - the newest 30 are kept, with an optional second folder;
  - the admin gets *Back up now* and *Download*.
- **Reports** (`app/routes_reports.py`):
  - attendance % per class and per student over a date range;
  - students below a chosen limit are highlighted;
  - a register CSV for Excel, with one column per session;
  - planned future sessions don't count.
- **Activity log** (`app/audit.py`):
  - every change is recorded with who, when, what and to whom;
  - the log entry is written in the same database transaction as the change;
  - the admin can search it.
- **HTTPS on the school network (later removed):**
  - The system made its own certificate (with the `cryptography` package), restricted to private network addresses.
  - While testing it, we found that **Norton 360** on the laptop intercepts HTTPS connections.
  - The feature was removed in stage 9, when the owner chose to host online, because hosts like Render, Railway and Fly.io provide HTTPS themselves.

## 9. Co-curricula, achievements, separate portals
The owner explained how the school's records work: each student has **three co-curricula** (uniform body, club/society, sport/game) and achievements, all in the school's list.
- **Master list = the students.**
  - Importing `student_no,name,class_id,uniform_body,club_society,sport_game` creates every student straight away (*not registered yet*).
  - It also creates each co-curriculum (a `classes` row with a category) and puts its members in it. Nobody adds students by hand.
  - Registering only adds the password and the QR.
- **One co-curriculum per category per student** (`accounts.set_cocu`).
  - A re-import moves students when their co-curriculum changes.
  - A column left out of the file is untouched; an empty cell removes that co-curriculum.
  - Members of a co-curriculum can't be changed by hand. Teachers can still make **groups** (e.g. seniors only).
- **Achievements:** a separate CSV `student_no,year,activity,level,award`. Malay level names also work (*Daerah* → District). Duplicates are ignored, and the student's profile shows them.
- **Teachers in charge** of each co-curriculum are assigned by the admin. The overview warns when a co-curriculum has none.
- **Reports and session counts** show *not registered yet* students separately, so they don't lower the percentages.
- **Separate portals:**
  - `/student` (also `/`), `/teacher` and `/admin`, each with its own log-in, registration and forgot-password page;
  - the student portal has no link to the others;
  - the admin does everything, including co-curricula, sessions, scanning and reports, inside the admin portal (`staff.html` shows tabs by role);
  - someone using the wrong address is sent to their own portal.
- **Ready for GitHub and Docker hosts:**
  - the container listens on the host's `PORT`;
  - it trusts the host's proxy for visitors' real addresses (each visitor gets their own rate limit);
  - it fixes permissions on the `/data` volume, then runs as an unprivileged user (`scripts/docker-entrypoint.sh`);
  - `.gitattributes` keeps Unix line endings for shell scripts.
- **Automatic upgrade:** older databases are upgraded on start. The old master-list table becomes student rows, and new columns are added. This was tested on a copy of the owner's real database.
- **Python or Angular:** Python was kept (see section 13).

## 10. Cinematic design
The owner supplied a *Cinematic UI Design System* specification (originally for a car showcase) and asked for that look in all three portals, with a different theme for each user.

**What was taken from the spec:**
| Spec idea | Where it is used |
|---|---|
| Scene black `#040407`, white / dim / whisper text, silver | Every page (`style.css` tokens) |
| One warm and one cold light per scene, as radial gradients (key, rim, ambient) | The fixed background of every page; each scene of the log-in pages and the student portal; each panel's corner glow |
| Full-bleed establishing shot, title card in the lower third | Scene 1 of the student portal (the log-in pages used it too, until they were simplified; see the readability pass below) |
| Scene label (tiny tracked capitals, number in the warm colour) + scene heading (huge, uppercase, 800 weight) + dim sub-line | All scenes; a title card at the top of every teacher/admin tab (e.g. *01 / Control room — OVERVIEW*) |
| Layered parallax (background 0.15, watermark 0.3, light rays 0.6, text 0) | Log-in pages and student portal (`cinema()` in `app.js`) |
| Scene progress: the background scales up and fades as the scene leaves (camera pulling back) | Every `.scene` (`--progress`) |
| Dramatic statistics in gradient text | The student's *Performance* scene; the number cards in the teacher and admin portals |
| Horizontal spec bars that fill left to right when seen | Achievements (longer bar = higher level) and every attendance % bar in reports |
| 2×2 technology grid with a 1px light separator | The student's three co-curricula, profile and groups |
| Minimal nav that fades in, tracked uppercase links | The header of every page and the tab bars |
| Sharp corners, no light mode, Inter typeface | Everywhere (Inter is bundled locally) |
| Kinetic micro-interactions on the call to action | Buttons lift and glow on hover |

**The three themes:** each keeps the spec's rule of exactly one warm and one cold light.
| Portal | Theme | Warm light | Cold light |
|---|---|---|---|
| Student | *Premiere* | gold `#C9A96E` | blue ice `#4A90D9` |
| Teacher | *Field* | copper `#D08C5E` | teal `#3FA79B` |
| Admin | *Control room* | ember `#C2604E` | steel `#8FA3B8` |

`app.js` reads the address and sets `html[data-role]`; `style.css` swaps the two lights.

**The student portal became a film in seven scenes:**
1. **Establishing:** the student's name, huge, with their class ID and co-curricula
2. **The pass:** the one-time QR, lit like a product shot (the QR card stays white so it scans)
3. **The ensemble:** the three co-curricula
4. **Performance:** sessions attended, honours, co-curricula as big numbers
5. **Every scene:** attendance list
6. **The honours:** achievements as spec bars
7. **That's you:** profile, change password, log out

**Where the spec was deliberately not followed, and why:**
- **Status colours:** the spec allows only two accents. A school system must show *present / absent / not registered / refused*, so muted green, red and amber are kept for status only.
- **Panels:** the spec says no cards inside scenes. The teacher and admin portals are working tools with forms and tables, so they keep thin, sharp, barely-lit panels. The full-screen scene treatment is used on the entrance pages and the student portal.
- **The QR card** is white on purpose: a QR needs dark modules on a light background to scan.
- **Reduce motion:** with the device's *reduce motion* setting on, all parallax and animation stop and everything shows at once.
- **Printing:** the page prints the QR only, on white.

### Readability pass (after feedback)
The first cinematic version copied the spec's very faint text: labels at 30% white on near-black, 9–10px tracked capitals, 1px outline headings. The project owner found it hard to read, which breaks a basic HCI rule: text must be readable. The style stayed the same and only the colours and sizes changed:

| | Before | After |
|---|---|---|
| Body text (`--dim`) | 58% white | 82% white (about 12:1) |
| Small labels (`--whisper`) | 30% white | 66% white (about 7:1) |
| Smallest text | 9px | 11px |
| Lines and borders | 7% / 14% white | 13% / 28% white |
| Outline word in big headings | 1px outline | Solid accent colour |
| Accent colours | Muted (e.g. admin #C2604E) | Brighter versions of the same hues (admin #FF8F78, student #F0C77F, teacher #FFAD78) |
| Status colours | Muted green, red, amber | Brighter, and always with a word, never colour alone |

The target is WCAG AA: text at least 4.5:1 against its background.

**Log-in, register and forgot password** were simplified at the same time. The big title scene was replaced by:
- one card in the middle, holding the school's crest, name, portal and form;
- a backdrop of the school's crest glowing softly, with the school name and motto drifting past in huge faint letters (decoration only).

The school is a made-up placeholder, *SMK Taman Harmoni*. Its name and motto are set in `SCHOOL` in `app.js`, and the logo is `app/static/school/crest.svg`.

## 11. Hierarchy, profiles and white-and-blue
The owner asked for ten changes, closer to how their previous school worked: students are recorded under a co-curriculum, the admin assigns teachers, and each teacher only sees and scans their own students.

| # | Request | What was done |
|---|---|---|
| 1 | Admin only *views* students and achievements | Removed the admin's add/edit/delete of single students, achievement import/add/remove, teacher registration/approval/passwords and account disabling. The admin keeps two uploads (students, teachers) and views everything. Corrections: fix the spreadsheet and upload again |
| 2 | Change password beside Log out | A **Change password** button in the header of every portal opens a dialog |
| 3 | Master list with Students and Teachers | **Master list** has two sub-tabs, each with its upload and its list. A new **teacher list** CSV: `teacher_id,name,position,email,co_curricula` |
| 4 | Admin report: overall only | The admin's report shows overall attendance, sessions held, co-curricula below 75% and one line per co-curriculum; no student detail |
| 5 | Teacher portal like the student's | A **profile page**: photo, teacher ID, name, position, email and the co-curricula they are in charge of (from the teacher list). Sessions can only include those, so the wrong one can't be selected |
| 6 | Profile pictures | Students and teachers upload their own photo. The page crops it to a square and shrinks it to 360 px; the server accepts only JPG/PNG/WebP up to 400 KB. Shown in the header, on profiles, in member lists and **on every scan result** |
| 7 | Stop a teacher recording a student outside their co-curriculum | Suggested and built, following the owner's school: rosters only from the student list; teachers in charge only from the teacher list; sessions only for own co-curricula; **teacher groups removed** (the one place an outside student could be added); scanning an outsider records nothing; the student's photo on each scan; **undo within 10 minutes**; every check-in and undo in the activity log |
| 8 | Teachers see only their own reports | Reports, student lists, achievements and photos are filtered to the teacher's own co-curricula on the server |
| 9 | Student portal focused on functions | Three pages instead of seven scenes: **Profile** (photo, ID, name, class, co-curricula, QR), **Attendance** (per co-curriculum % and sessions) and **Achievements** |
| 10 | White with blue | `style.css` rewritten: white cards on a light grey-blue page, one blue accent per portal (student bright blue, teacher ocean blue, admin navy), all text at least 4.5:1 |

Achievements are now recorded by the teacher in charge, for a member of their own co-curriculum, as decided with the owner. The teacher and admin portals became two separate pages (`teacher.html`, `admin.html`) instead of one page with tabs by role, because their jobs are now so different.

**Upgrading:** an existing database keeps working. Old teacher accounts stay registered (with an empty position until the teacher list is uploaded). Sign-ups that were never approved become teacher-list entries that must register. Groups made earlier remain, but no new ones can be made.

### Split classes (two teachers, same co-curriculum, same time, different halls)
**Testing the scenario first:** the owner asked whether two teachers can run the same co-curriculum at the same time in different venues. A test on 30 sample students showed:
- **Two separate sessions:** each expected all 14 band members, so each hall showed 7 absent, and the report fell to about 50%.
- **One shared session:** gave the right answer, 14 present.

Two changes followed:
1. **Overlapping sessions are refused.** A second session for the same co-curriculum at an overlapping time is rejected, with a **Join that session instead** button.
2. **My venue.** Each teacher sets their hall in the shared session, and every check-in records it. It shows in the list, the CSV and the student's history.

## 12. Bugs found and fixed
| Bug | Cause | Fix |
|---|---|---|
| Students could not register/log in (original problem) | Old version | Rebuilt (section 2) |
| Editing a master-list entry made a duplicate | Saved by the new ID instead of the original | Edit by original ID (section 6) |
| Calendar missed the last day of some months | The month start kept the time of day, so the loop stopped a day early | Build the month start at midnight |
| Typing in the class search before it loaded threw an error | Search ran before the class arrived | Wait for the class; reset it when switching |
| A session header showed a raw link address | The DOM helper flattened only one level of nested content | Flatten all levels |
| A scan could go to the previous session while a new one loaded | The session was still set from before | Clear it on every route change |
| Scan result animation did not replay for two successes in a row | Same CSS class twice | Reset the class and force a reflow |
| Student profile showed `uniform` instead of `Uniform body` | Dictionary merge order | Put the readable label last |
| A comment in one line of JavaScript broke the whole teacher page | `//` comment swallowed the rest of the line | Comment moved to its own line; a syntax check now runs on every page |
| Extra `)` in the master-list table | Typo | Found by the syntax check |
| Phone landing page gradient stopped half-way | `background-attachment: fixed` on full-page height | Gradient on the whole page |

## 13. How everything was tested
- **Automated tests (`python -m pytest -q`): 30 tests.**
  - `test_flow.py`: registration of students and teachers, QR once, roles, the admin only uploading and viewing, teachers limited to their own co-curricula, joint sessions, scan results, undo, forgot password, addresses.
  - `test_cocurricula.py`: co-curricula from the student list, the teacher list, achievements by teachers, photos, portal addresses, upgrading an old database.
  - `test_extras.py`: reports (teacher detail, admin overall), activity log, backups.
- **Browser test:** a Playwright script drives Microsoft Edge through the whole story and fails on any JavaScript error:
  1. the admin uploads the sample student and teacher lists, and has no edit buttons;
  2. a teacher registers with a teacher ID, sees position and co-curricula, uploads a photo, and changes password in the header dialog;
  3. students register, upload a photo, and print their QR;
  4. the teacher creates a session (only their own co-curricula are offered);
  5. scans: success with the photo, undo, again, and an outsider refused with nothing recorded;
  6. *My students* shows only their own students;
  7. the teacher records an achievement, and the student sees it on the Achievements page;
  8. the student sees attendance;
  9. the admin sees the co-curriculum (view only), achievements, the overall report and the log;
  10. phone width.
- **Screenshots** of every portal were reviewed after each design change.
- **JavaScript syntax check** of every page, using Node.js.
- **GitHub Actions** runs the tests and builds the Docker image on every push.
- **Not yet tested:** building and running the Docker image (Docker is not installed on the development laptop; GitHub Actions builds it on the first push), and camera scanning on a real phone over HTTPS.

## 14. Key decisions
- **Python (FastAPI) + plain JavaScript, not Angular.**
  - Angular would only replace the pages; a server like this one would still be needed.
  - Without a build step, the whole system is one small Docker image that anyone can run and read.
  - The API stays the same, so the pages could be rebuilt in a framework later.
- **SQLite.** One school fits easily, simultaneous scans are safe, and a backup is one file.
- **Master list as user rows.** Rosters and teacher assignments exist before anyone registers, and there is no second copy of the lists to keep in step.
- **Admin uploads, teachers act.** Teachers are put in charge only through the uploaded teacher list, so the school office's list and the system can't drift apart, and no teacher can choose someone else's co-curriculum.
- **No passwords sent by email to students.** Students have no school email, so reset codes are given in person by a teacher.
- **Hosting:** GitHub stores the code, and a Docker host provides the server and HTTPS. A persistent volume at `/data` keeps the data.
