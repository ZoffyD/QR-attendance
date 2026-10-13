# Deployment

| Situation | What to do |
|---|---|
| **Show it on one laptop** | `scripts\start-windows.bat`, then http://localhost:8000/student, `/teacher` and `/admin`. The camera works on `localhost`. |
| **Online demo, from GitHub** | A Docker host connected to the GitHub repository (Render, Railway, Fly.io…). HTTPS is included, so phones can scan. See [below](#online-from-github-with-docker). |
| **School owns a domain / own server** | `docker compose --profile https up -d` with Caddy: edit `Caddyfile` with the domain. Caddy gets a free certificate by itself. Ports 80 and 443 must reach the server. |
| **School network, no internet** | `docker compose up -d` on a PC in the school (port 8000) and **USB QR scanners**: browsers block the camera on plain `http://` addresses other than localhost. |

## Online from GitHub with Docker

GitHub Pages only hosts static files, so it can't run this system. Instead:
1. Push the project to GitHub.
2. Connect the repository to a host that builds Docker images.

The `Dockerfile` works as it is:
- It listens on the `PORT` the host gives it.
- It trusts the host's proxy for visitors' real addresses.
- It stores everything in `/data`.

### Settings on the host
| Setting | Value |
|---|---|
| Build | from the `Dockerfile` in the repository root |
| Environment variable `ATT_ADMIN_PASSWORD` | a long password: used once, to create the `admin` account |
| Environment variable `TZ` | `Asia/Kuala_Lumpur` (session dates and backups use local time) |
| **Persistent volume / disk** | mounted at **`/data`** (1 GB is plenty) |
| Health check path (optional) | `/healthz` |

**The persistent volume is essential.** Without it, the database lives inside the container and is **wiped on every restart or redeploy**. Some free plans have no persistent storage; check your host's current plans and pricing. Without a volume, it's still fine for a short demo: upload the sample CSVs again after a restart.

After the first deploy:
1. Open `https://<your-app>/admin` and log in as `admin`.
2. Go to **Master list → Students** and upload `scripts/sample_students.csv`.
3. Go to **Master list → Teachers** and upload `scripts/sample_teachers.csv`.
4. Teachers and students register once at `/teacher` and `/student` (e.g. teacher `T001` *Eren Yeager*, student `13255` *Vicky Tan*).

Give each group its own link:
- **Students:** `https://<your-app>/student` (or just the bare address)
- **Teachers:** `https://<your-app>/teacher`
- **Admin:** keep `https://<your-app>/admin` to yourself

### Keep it private
A public URL can be found by anyone. For a demo, use only sample data, not real students. For real use, read [PRIVACY.md](PRIVACY.md): the school must approve where student data is stored.

### Email for forgot password (optional)
Set `ATT_SMTP_HOST`, `ATT_SMTP_PORT`, `ATT_SMTP_USER`, `ATT_SMTP_PASSWORD`, `ATT_SMTP_FROM` (for Gmail: host `smtp.gmail.com`, port 587, an App Password) and `ATT_ADMIN_EMAIL`. Without email, teachers' and the admin's codes appear in the host's **logs**. The admin can also set a teacher's password directly, and students always get their code from a teacher.

## Windows: first install (local)

Needs Python 3.10 or newer.
1. Open PowerShell in the project folder.
2. Run `pip install -r requirements.txt`.
3. Double-click `scripts\start-windows.bat`. The first start asks you to choose the admin password.
4. Open http://localhost:8000/admin and log in as `admin`.

Keep the window open while the system is in use.

## Backups

The server backs up the database by itself: every `ATT_BACKUP_HOURS` (24 by default) into `data/backups` (in Docker, `/data/backups` on the volume), keeping the newest `ATT_BACKUP_KEEP` (30). The backup is consistent even while teachers are scanning.

In the admin portal, **Overview → Backups** shows the last backup and has **Back up now** and **Download** buttons. A warning appears if the newest backup is more than two days old.

- **Keep a copy elsewhere:** download a backup regularly, or set `ATT_BACKUP_COPY_DIR` to a second disk or mounted folder.
- **Restore:**
  1. Stop the app.
  2. Copy the backup over `data/attendance.db`.
  3. Delete `attendance.db-wal` and `attendance.db-shm` if they exist.
  4. Start the app again.

  With Docker Compose, `scripts/restore.sh` does this.

Backups contain every student's data: store them like the original.

## Updating

Copy the new files over the old ones (or `git pull`), keep the `data` folder or volume, and run `pip install -r requirements.txt` again, or redeploy the container. New tables are added automatically at start-up. A database from an older version, which had a separate master-list table, is converted automatically.
