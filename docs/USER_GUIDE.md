# QR Attendance: user guide

This guide shows the school admin, teachers and students how to use the system, step by step. Each role has its own address. If the system runs at `https://attendance.example.com`, the addresses are:

| You are | Open |
|---|---|
| Student | `https://attendance.example.com/student` (or just the bare address) |
| Teacher | `https://attendance.example.com/teacher` |
| Admin | `https://attendance.example.com/admin` |

**Contents**
1. [How the system works](#1-how-the-system-works)
2. [Admin](#2-admin)
3. [Teacher](#3-teacher)
4. [Student](#4-student)
5. [Forgot password](#5-forgot-password)
6. [Common situations](#6-common-situations)
7. [Messages you may see](#7-messages-you-may-see)

---

## 1. How the system works

```
 Admin                              Teacher                               Student
 ─────                              ───────                               ───────
 1. uploads the student list:       3. registers once (teacher ID          2. registers once (student ID
    ID, name, class ID, uniform        + name on the teacher list)            + name on the student list),
    body, club, sport               4. sees their profile: position and       prints the QR once
    → co-curricula + members           the co-curricula they run
 2. uploads the teacher list:       5. creates sessions for THEIR          7. sees profile, attendance
    ID, name, position,                co-curricula only                      and achievements
    co-curricula in charge          6. scans QR at the session ──────────►
 then only views                       records achievements
```

| Word | Meaning |
|---|---|
| **Master list** | The school's official lists, uploaded by the admin: **students** (student ID, full name, class ID, three co-curricula) and **teachers** (teacher ID, name, position, co-curricula in charge). |
| **Class ID** | The student's school class, such as 4E1, 5S4 or 3E. |
| **Co-curriculum** | A uniform body (e.g. *Gadet Police*), club or society (e.g. *Pancaragam Harmonica*) or sport or game (e.g. *Basketball*). Its members come from the student list; its teachers from the teacher list. |
| **Teacher in charge** | A teacher who runs a co-curriculum. There can be several. |
| **Session** | One meeting at a venue, date and time. Attendance is taken per session. |
| **Joint session** | One session for several of a teacher's co-curricula together. All their teachers in charge can scan into it. |
| **Not registered yet** | The person is on the master list but has not registered, so they can't log in (students: have no QR yet). |
| **Terminate QR** | Stops a lost QR from working. The student then registers again for a new one. |

**Who does what**

| | Admin | Teacher | Student |
|---|---|---|---|
| Upload the student and teacher lists | ✔ | | |
| View every student, teacher, co-curriculum and achievement | ✔ | | |
| Overall report, activity log, backups | ✔ | | |
| Profile with photo | | ✔ | ✔ |
| Sessions, scanning, undo a wrong check-in | | own co-curricula | |
| Record achievements | | own co-curricula | |
| Reset code and Terminate QR for students | | own students | |
| Detailed report per student | | own co-curricula | |
| Print own QR, see own attendance and achievements | | | ✔ |
| Change password (top of every page) | ✔ | ✔ | ✔ |

---

## 2. Admin

Open `/admin` and log in with the username `admin` and the password chosen at the first start. The admin **uploads the master list and views everything**. The admin does not add, edit or delete single students, achievements or sessions. To correct something, fix the school's spreadsheet and upload it again.

### 2.1 First-time setup
1. **Change your password:** **Change password** at the top right.
2. **Upload the student list:** **Master list → Students**. Choose a CSV file (Excel: *File → Save As → CSV UTF-8*) with this header row and press **Upload**:
   ```
   student_no,name,class_id,uniform_body,club_society,sport_game
   13255,Vicky Tan,4E1,Gadet Police,Pancaragam Harmonica,Basketball
   ```
   Every co-curriculum is created the first time it appears, with these students as members. Rows that can't be used are listed with the reason, e.g. *line 7: student ID is empty*. Sample: `scripts/sample_students.csv`.
3. **Upload the teacher list:** **Master list → Teachers**, after the student list:
   ```
   teacher_id,name,position,email,co_curricula
   T001,Eren Yeager,Senior Assistant,eren@school.edu.my,Gadet Police; Basketball
   ```
   - **co_curricula:** the co-curricula the teacher is in charge of, separated by `;`. The names must match the student list exactly; a name that doesn't is reported and that row is skipped.
   - **email** is optional. Teachers give their own when they register.
   - Sample: `scripts/sample_teachers.csv`.
4. **Tell teachers and students** to register once: teachers at `/teacher` → *First time? Register*, students at `/student` → *First time? Register*.

### 2.2 Overview
- **Numbers:** students registered out of the list, teachers registered out of the list, co-curricula, sessions, check-ins and achievements.
- **Yellow alerts** when something needs you: a list is empty, co-curricula have no teacher in charge, or there is no recent backup.
- **Backups:** see 2.7.

### 2.3 Master list: Students and Teachers
Two sub-tabs, **Students** and **Teachers**. Each has the upload box and the full list with account status (*registered* or *not registered yet*). Search by ID, name, class ID, position or co-curriculum. Tick *Only not registered yet* to see who still has to register.

**New school year:** upload the new files. People are updated and new ones added; accounts, QR codes and attendance stay.
- A column left out of the file is not changed.
- An empty cell removes that co-curriculum (or, for teachers, all their co-curricula).

### 2.4 Co-curricula
Every co-curriculum with its type, teachers in charge, members and sessions. **View** shows the teachers (with position), the members and their account status.

### 2.5 Achievements
Every achievement recorded by teachers, with who recorded it. Search by student, activity, level or award.

### 2.6 Report and activity log
- **Report:** the overall picture only, for any period:
  - overall attendance, sessions held, number of co-curricula and how many are below 75%;
  - every co-curriculum with its attendance bar.

  Teachers see the student-by-student detail of their own co-curricula.
- **Activity log:** who did what and when, for example *"Eren Yeager — Checked in — Vicky Tan (13255)"* or *"Eren Yeager — Undid check-in — …"*. Search for a student, teacher, co-curriculum or action.

### 2.7 Backups
The system backs itself up every day. **Overview → Backups** shows the last backup. Use **Back up now** before big changes, such as uploading a new master list, and **Download** to keep a copy on a USB drive. To restore a backup, see [DEPLOYMENT.md](DEPLOYMENT.md#backups).

---

## 3. Teacher

### 3.1 Register (only once)
1. Open `/teacher` and press **First time? Register**.
2. Enter your **teacher ID** and **full name exactly as in the school's teacher list**, your email (for forgot password) and a password (8 or more characters).
3. Press **Register**. Your position and co-curricula appear automatically.

If you see *"Your teacher ID and name do not match the school's teacher list"*, check the spelling, or ask the admin.

### 3.2 Profile (your home page)
- Your **photo**: press **Upload photo** (or **Change photo**). It is cropped to a square. The admin and the other teachers of your co-curricula can see it; students can't.
- **Teacher ID, name, position and email.**
- **Co-curricula you are in charge of**, from the school's teacher list. Each shows its members, how many registered, and its sessions, with **Open** and **+ New session**. You can only work with these, so you can't choose someone else's by mistake. If one is missing or wrong, ask the admin.

### 3.3 Calendar
Every session of your co-curricula, with time and venue. Today is outlined.
- Click a session to open it.
- Click a day number, or **+ New session**, to create one.

### 3.4 Create a session and take attendance
1. Press **+ New session** on a co-curriculum (it is ticked for you), or click a day in the calendar.
2. Enter a **title** (e.g. *Weekly practice*), the **venue**, **date**, and start and end time.
3. Under **Co-curriculum**, only yours are listed. Tick several for a joint session.
4. Press **Save session**. The session page opens.
5. Scan the students' QR codes:
   - **Camera:** press **Start camera** and hold the QR in front of it. This needs an `https://` address.
   - **USB scanner:** click the box *USB scanner: click here and scan* and scan.

| Result | Meaning |
|---|---|
| 🟩 **Check-in successful** | The student is a member and is now present. Their **photo** shows, so you can check it is really them. |
| 🟨 **Already checked in** | Scanned before, by you or another teacher. |
| 🟥 **Student is not involved in this session** | The student is not a member of this session's co-curricula. **Nothing is recorded.** |
| 🟥 **QR code not recognised, or it was terminated** | The QR was terminated or is not from this system. |
| 🟥 **This session is closed** | Press **Reopen session** to scan more. |

- **Split class** (one co-curriculum too big for one room, e.g. the band in Hall A and Hall B at the same time, each with its own teacher):
  1. One teacher creates **one** session with every hall in the venue, e.g. `Hall A / Hall B`.
  2. The other teacher in charge sees it on their calendar and opens it on their own device.
  3. Each teacher fills in **My venue** (e.g. *Hall B*) before scanning. A session with several halls refuses to scan until you do, and your device remembers it.
  4. Every check-in records the hall. The list, the CSV and the student's history show where each student was.

  A **second session for the same co-curriculum at an overlapping time is refused**: it would mark the students in the other hall as absent. The message offers **Join that session instead**.
- **Undo:** a check-in made by mistake can be undone with **Undo** on its row for **10 minutes**, while the session is open. Check-ins and undos are kept in the admin's activity log.
- The numbers show **present**, **absent** and **not registered yet**. The list updates by itself every few seconds, so scans from other teachers' devices appear too.
- **Close session** stops more scans. **Edit / reschedule** changes the venue, date, time or co-curricula. **Export CSV** downloads the list.

### 3.5 My students
The students of your co-curricula only.
- **Terminate QR:** when a student reports their QR lost. The old QR stops working at once, and the student registers again for a new one. Their history is kept.
- **Reset code:** when a student forgot their password (marked *asked for password reset*). Check it is really the student, press **Reset code**, and tell them the 6-digit code in person.

### 3.6 Achievements
1. Choose the **co-curriculum** (yours only) and the **student** (its members only).
2. Enter the **year**, **level** (School, Zone, District, State, National or International) and **award** (e.g. *Champion*).
3. Press **Record**.

The achievement appears on the student's profile. The list below shows every achievement in your co-curricula, with **Remove** if one was recorded by mistake.

### 3.7 Reports (your co-curricula only)
1. Choose a co-curriculum, the **From** and **To** dates (from 1 January by default) and **Highlight below** (75% by default).
2. **All mine (summary)** compares your co-curricula.
3. One co-curriculum shows:
   - the totals;
   - every student with *attended / held* and a bar (amber when close to the limit, red below it). Tick **Lowest first** to see who needs attention;
   - every session with how many were present.
4. **Export CSV (Excel)** downloads a register: one row per student, one column per session (1 = present, 0 = absent).

Only sessions that have already happened count. Students who have not registered yet can't be scanned, so they are listed but left out of the percentages.

---

## 4. Student

### 4.1 Register (only once)
1. Open `/student` and press **First time? Register**.
2. Enter your **student ID** and **full name exactly as in the school's records**, then create a password (8 or more characters).
3. Press **Register**. Your class ID and co-curricula appear automatically.

### 4.2 Profile
- Your **photo**: press **Upload photo**. Your teachers see it when they scan your QR, to check it is you, so use a clear photo of your face.
- **Student ID, name and class ID.**
- **My co-curricula:** your uniform body, club/society and sport/game, with their teachers.
- **My QR code:** press **Show and print my QR (one time only)**, then **Print** or **Save image**. It is shown **only once**, so do this before leaving the page. Bring it to every activity.

### 4.3 Attendance
- **By co-curriculum:** sessions held so far, how many you attended, and your percentage.
- **Sessions attended:** every session you were scanned at, with venue, scheduled time and check-in time.

### 4.4 Achievements
Year, activity, level and award, as recorded by your teachers.

### 4.5 Lost QR
Tell your teacher. They terminate the old QR, and then you **register again** with the same student ID and name to get a new QR. Your attendance history is kept.

---

## 5. Forgot password

On your portal's log-in page, press **Forgot password?**

| You are | Step 1: ask for a code | Step 2 |
|---|---|---|
| **Student** | Enter your student ID and press **Request reset code**. Then ask your co-curriculum teacher for the 6-digit code. | Enter your student ID, the code and a new password. |
| **Teacher / Admin** | Enter your teacher ID (admin: username) or email and press **Request reset code**. The code is emailed to you. If email is not set up, ask the person who runs the server: it appears in the server log. | Enter your ID, the code and a new password. |

The code works **once**, for **30 minutes**, and is locked after 5 wrong tries.

To change a password you know, use **Change password** at the top of any page.

---

## 6. Common situations

| Situation | What to do |
|---|---|
| A student or teacher can't register | Check they are on the **master list** with the right spelling (admin: Master list). |
| A student is missing from a co-curriculum | Their co-curriculum in the student list is different or empty. Fix the spreadsheet and upload it again. |
| A teacher sees no co-curricula | The teacher list has no co-curricula for them, or the names don't match the student list. Fix and upload again. |
| "Student is not involved" but they should be | Their co-curriculum in the student list is wrong. Fix and upload again. |
| Scanned the wrong student | Press **Undo** on their row within 10 minutes. |
| A student shows as *not registered yet* | They have to register once at `/student` before they can be scanned. |
| Student lost the QR | **Terminate QR** (My students); the student registers again. |
| Two teachers scanning at the same time | Fine: both go into the same list, and a student is never counted twice. |
| Camera won't start | The address must start with `https://`, and the browser must be allowed to use the camera. Otherwise use a USB scanner. |
| Which students skip activities? | Teacher: **Reports** → choose the co-curriculum → tick **Lowest first**. |

## 7. Messages you may see

| Message | Meaning |
|---|---|
| *This student ID is already registered, and a student can register only once…* | Log in instead. If the QR is lost, ask a teacher to terminate it, then register again. |
| *Wrong username or password* | Check your ID and password. If you never registered, press **First time? Register**. |
| *Your QR code was terminated by your teacher. Please register again…* | Register again to get a new QR. |
| *Your QR code was already printed…* | The QR is shown only once. If it is lost, ask a teacher to terminate it. |
| *You can only create sessions for the co-curricula you are in charge of* | Only your own co-curricula can be in a session. |
| *… already has a session at that time … join that session instead* | Another teacher in charge already made a session then. Press **Join that session instead** and scan into it with your own venue. |
| *Choose your venue first* | The session is in several halls. Fill in **My venue** above the scan box. |
| *A check-in can only be undone within 10 minutes…* | Too late to undo. The check-in stays, and the activity log shows who scanned it and when. |
| *'…' is not a co-curriculum on the student master list* | Admin: a co-curriculum name in the teacher list doesn't match the student list. |
| *This is a student account. Please use the Student login.* | You used another role's address. Use your own (`/student`, `/teacher` or `/admin`). |
| *Too many attempts. Please wait a few minutes…* | Too many wrong tries. Wait 10 to 15 minutes, then try again. |
