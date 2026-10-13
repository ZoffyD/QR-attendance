# Privacy notes

This system handles students' personal data. Check it against your school's policy and Malaysia's Personal Data Protection Act (PDPA). This is a technical checklist, not legal advice.

## What is stored
- **The student list**, uploaded by the admin: student ID, full name, class ID and three co-curricula (uniform body, club/society, sport/game) for every student, including those who never register.
- **The teacher list**, uploaded by the admin: teacher ID, full name, position, email (optional) and the co-curricula each teacher is in charge of.
- **Students who registered:** a hashed password they chose, the time they registered, and when they printed their QR.
- **Teachers who registered:** their email (for forgot password), a hashed password, and the time they registered.
- **Profile photos**, if a student or teacher uploads one: one picture per person, shrunk to 360 × 360 pixels, stored inside the database.
- **QR tokens:** a random token for each registered student (inside the QR). It is not derived from the name or ID.
- **Activity records:** sessions (title, venue, date, time), check-in times and which teacher scanned.
- **Achievements**, recorded by teachers: year, activity, level, award, and who recorded them.
- **An activity log:** who did what and when, e.g. "Eren Yeager checked in Vicky Tan (13255)". It holds names and IDs, not passwords, codes or photos, and only the admin can read it.
- **Backups:** full copies of the database, photos included, in the backup folder (and the second folder, if set).

Not stored: location, phone numbers, addresses, birth dates, student email addresses.

## Who can see what
| Data | Student | Teacher | Admin |
|---|---|---|---|
| Own profile, attendance, achievements | ✔ | ✔ (own profile) | |
| Students of a co-curriculum, their photos and attendance | | only their own co-curricula | all |
| Other teachers' photos | | only teachers sharing a co-curriculum | all |
| Achievements | own | their co-curricula | all |
| Reports | | detail for own co-curricula | overall summary only |
| Activity log, backups | | | ✔ |

## Protections built in
- **Passwords:** stored hashed with scrypt; wrong log-in guesses are rate-limited.
- **Registration:** only an ID and name on the school's master list can register, and wrong guesses are rate-limited. The error does not say whether the ID or the name was wrong.
- **Register once:** a student can register again only after a teacher terminates the QR.
- **QR printed once:** copies cannot be made later for someone else to scan. Terminating a QR stops it working at once and logs the student out; past attendance is kept.
- **Teachers only reach their own co-curricula,** on the server, not just in the pages. Students see only their own record.
- **Photos:** only real pictures (JPG, PNG or WebP, checked by content), at most 400 KB, and only shown to the people in the table above. A student or teacher can remove their photo at any time.
- **Forgot-password codes:** random, 6 digits, work once, expire after `ATT_RESET_MINUTES` (30 by default) and are locked after 5 wrong tries. Students get theirs in person from one of their teachers. The forgot page gives the same answer whether or not an account exists.
- **Activity log:** every change, check-in and undo is recorded, so mistakes and misuse can be traced.

## Your responsibilities
- **Demo:** use only sample data (as in `scripts/sample_*.csv`), not real people, on a public demo address.
- **Real use:** the school must agree where the data is hosted (school server or a cloud host and its region).
- **Photos:** decide whether photos are allowed, and tell students and parents why they are used (checking identity at the scan) and who sees them.
- **HTTPS:** use a cloud host's address, or Caddy with the school's domain.
- **Admin access:** use a long admin password, keep `.env` and the host's environment settings private, and keep the `/admin` address to yourself.
- **Backups:** keep them somewhere restricted, because they hold the same data, photos included. Delete downloaded copies you no longer need.
- **Tell students and teachers** what is collected, why, and who can see it.
