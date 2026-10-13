# Sources: where everything comes from

This page lists every outside source used to build the system: data, code libraries, the font, the design reference and the ideas behind the security. Nothing else was copied from elsewhere. All application code (Python, HTML, CSS and JavaScript) was written for this project.

## 1. Data
| Data | Source |
|---|---|
| Students: student ID, full name, class ID, uniform body, club/society, sport/game | The school's student list, uploaded by the admin as a CSV file |
| Teachers: teacher ID, name, position, email, co-curricula in charge | The school's teacher list, uploaded by the admin as a CSV file |
| Profile photos | Uploaded by each student or teacher |
| Achievements: year, activity, level, award | Recorded by the teacher in charge of the co-curriculum |
| Attendance | Created when a teacher scans a student's QR |
| Sample data in `scripts/sample_students.csv` and `scripts/sample_teachers.csv` | Made up for demonstration; not real people (the teacher names are borrowed from anime characters as obvious placeholders) |

While the system runs, nothing is downloaded from or sent to any outside service, except forgot-password emails if you set up SMTP yourself.

## 2. Open-source libraries
| Part | Version | Used for | Licence | Where it comes from |
|---|---|---|---|---|
| Python | 3.10+ | Programming language of the server | PSF | python.org |
| FastAPI | ≥ 0.115 | Web API (routes, validation, `/docs`) | MIT | PyPI (`requirements.txt`) |
| Starlette | (with FastAPI) | Web framework underneath FastAPI, static files | BSD-3-Clause | PyPI |
| Uvicorn | ≥ 0.30 | Web server that runs the app | BSD-3-Clause | PyPI |
| Pydantic | v2 (with FastAPI) | Checking incoming data | MIT | PyPI |
| Segno | ≥ 1.6 | Making the QR code images (SVG) | BSD | PyPI |
| SQLite | built into Python | Database | Public domain | Python standard library (`sqlite3`) |
| Python standard library | | Password hashing (`hashlib.scrypt`), random tokens (`secrets`), CSV, backups (`sqlite3.backup`), email (`smtplib`) | PSF | python.org |
| html5-qrcode | 2.3.8 | Reading QR codes with the camera | Apache-2.0 | npm; a copy is bundled in `app/static/vendor/` so it works offline |
| Inter (variable font, latin) | 5.0.8 | The typeface of every page | SIL Open Font License 1.1 (`app/static/vendor/inter/LICENSE.txt`) | rsms/inter, downloaded from the `@fontsource-variable/inter` package on jsDelivr and bundled in `app/static/vendor/inter/`, so pages never contact Google Fonts |
| pytest, httpx | ≥ 8, ≥ 0.27 | Automated tests (development only) | MIT, BSD-3-Clause | PyPI (`requirements-dev.txt`) |
| Docker image `python:3.12-slim` | | Base of the container | Various open-source (Debian, Python) | Docker Hub |
| Caddy (optional) | 2 | Automatic HTTPS when the school has a domain | Apache-2.0 | Docker Hub |
| GitHub Actions `actions/checkout`, `actions/setup-python` | v4, v5 | Running the tests on every push | MIT | GitHub |

The licences of the Python packages, html5-qrcode and Inter were read from the package metadata, the npm registry and the font's licence file. The SQLite, Docker and Caddy rows are from general knowledge; check current terms before commercial use.

**Testing tools (not part of the system):**
- Playwright, used to drive Microsoft Edge in the browser tests
- Node.js, used to check the pages' JavaScript for syntax errors

## 3. Design
| Element | Source |
|---|---|
| Current look: white and blue, one blue shade per portal (student bright blue, teacher ocean blue, admin navy) | Requested by the project owner; designed for this project |
| Earlier cinematic look (dark scenes, warm and cold lights; replaced) | The *Cinematic UI Design System* specification supplied by the project owner, adapted to a school system (see [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md#10-cinematic-design)). Its log-in card with the school crest and drifting school name was kept |
| Icons (QR logo) | Drawn for this project as inline SVG |
| School crest and name (*SMK Taman Harmoni*, `app/static/school/crest.svg`) | A made-up placeholder drawn for this project, not a real school. Replace it with the school's own logo |
| Colour contrast targets | WCAG 2.x level AA (text 4.5:1), applied from general knowledge of the guideline |
| Earlier light design (before the cinematic one) | Designed for this project |

## 4. Security and privacy practice
No web pages were looked up for the security design. It follows widely known practice:
- hashed passwords with a slow hash (scrypt)
- long random tokens that contain no personal data
- rate limiting of guesses
- single-use, short-lived reset codes with a limit on wrong tries
- answers that don't reveal whether an account exists
- an activity log

For a report, the **OWASP Authentication Cheat Sheet** and **Password Storage Cheat Sheet** describe these ideas. They were *not* consulted while building this, so read them yourself before citing them.

The privacy checklist refers to Malaysia's **Personal Data Protection Act 2010 (PDPA)** by name only. It is not legal advice.

## 5. How it was built
The system was written with an AI coding assistant (Claude, in Claude Code), following the project owner's requirements step by step. Each step was checked with automated tests (`tests/`) and a browser test in Microsoft Edge. The full history is in [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md).
