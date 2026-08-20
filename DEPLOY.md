# Production deployment

Target: a single Ubuntu VPS (e.g. Contabo Cloud VPS), Docker Compose,
nginx terminating TLS in front of uvicorn (Django) and the built React
admin panel. Telegram requires a real HTTPS domain for webhooks — a bare
IP will not work.

## 0. Prerequisites

- A domain name, with an **A record pointing its root (or a subdomain) at
  the server's IPv4 address**. DNS propagation can take a few minutes to a
  few hours — confirm with `dig +short your-domain.com` before continuing.
- SSH access to the server as `root` (or a user with sudo).

## 1. Initial server setup

SSH in, then:

```bash
apt update && apt upgrade -y

# Non-root user for daily use — avoid staying logged in as root.
adduser deploy
usermod -aG sudo deploy
```

Log out and back in as `deploy` for the rest of this guide.

Firewall — only SSH, HTTP, HTTPS are ever exposed (Postgres/Redis/etc. stay
internal to the Docker network, `docker-compose.prod.yml` never publishes
their ports):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Install Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
# log out and back in again so the group membership takes effect
docker compose version   # sanity check
```

## 2. Get the code

```bash
git clone https://github.com/Reaktiv/pharmacy-cashback.git
cd pharmacy-cashback
```

## 3. Create `.env`

`localhost` in `ALLOWED_HOSTS` below is required, not optional: the `web`
container's own healthcheck (`docker-compose.prod.yml`) calls
`http://localhost:8000/healthz/` from inside the container itself, and
Django's ALLOWED_HOSTS check rejects that Host header with a 400 if only
the real domain is listed — which Docker then reports as "unhealthy" even
though the app is actually fine. Port 8000 is never published outside the
Docker network (only nginx's 80/443 are), so this doesn't widen what's
reachable from the internet.

```bash
nano .env
```

```bash
DJANGO_SETTINGS_MODULE=config.settings
SECRET_KEY=            # python3 -c "import secrets; print(secrets.token_urlsafe(50))"
DEBUG=False
ALLOWED_HOSTS=your-domain.com,localhost
CSRF_TRUSTED_ORIGINS=https://your-domain.com

FERNET_KEY=            # python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

DATABASE_URL=postgres://pharmacy:CHANGE_ME@db:5432/pharmacy_cashback
POSTGRES_DB=pharmacy_cashback
POSTGRES_USER=pharmacy
POSTGRES_PASSWORD=CHANGE_ME

REDIS_URL=redis://redis:6379/0

PUBLIC_BASE_URL=https://your-domain.com

# Required if this server is NOT hosted in Uzbekistan. ofd.soliq.uz (the
# fiscal receipt lookup apps/bot/tasks.py's Playwright browser calls)
# silently drops connections from foreign IPs at the TCP handshake —
# confirmed by hand: a raw TCP connect and curl both time out from a
# France-hosted VPS while the same URL responds in ~20ms from an Uzbek ISP,
# and general internet access from that same VPS is otherwise fine (so
# it's specifically ofd.soliq.uz blocking the server's IP/ASN, not a
# broken network). Point this at an Uzbekistan-based HTTP/SOCKS5 proxy —
# only this one outbound call is routed through it, nothing else the app
# does. Leave blank if the server itself already has an Uzbek IP (or
# reachability is otherwise confirmed — see the curl test below).
OFD_PROXY_URL=
OFD_PROXY_USERNAME=
OFD_PROXY_PASSWORD=
```

Before going live, confirm the server can actually reach ofd.soliq.uz —
this fails silently otherwise (the customer just sees "chekni tekshirib
bo'lmadi", indistinguishable from any other transient failure):

```bash
curl -s -o /dev/null -w '%{http_code} in %{time_total}s\n' --max-time 10 https://ofd.soliq.uz/
```

`000` / a 10s timeout means the server's IP is blocked and `OFD_PROXY_URL`
above is required; a fast `200` (or any real HTTP status) means it isn't.

Generate the two secrets on the server itself (needs Python — either
`python3` from the OS, or skip and generate them locally and paste in):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use a strong, unique `POSTGRES_PASSWORD` — it's only ever used inside the
Docker network, but treat it as a real credential.

## 4. Point nginx at your domain

```bash
mkdir -p certbot/www certbot/conf
sed "s/__DOMAIN__/your-domain.com/g" nginx/bootstrap.conf > nginx/active.conf
```

(Replace `your-domain.com` with your real domain in every command below,
too.)

## 5. First boot (HTTP only, no cert yet)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This builds and starts everything: Postgres, Redis, `web` (runs migrations
+ collectstatic automatically on start, then uvicorn), `worker`, `beat`,
`frontend-build` (builds the React app once into a shared volume), `nginx`
(currently on the bootstrap HTTP-only config), and `certbot` (idle renew
loop — nothing to renew yet).

Check everything is healthy:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs web --tail 50
```

`http://your-domain.com/` should now respond with `bootstrap ok`.

## 6. Get the TLS certificate

```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  -d your-domain.com \
  --email you@example.com --agree-tos --no-eff-email
```

If that succeeds, switch nginx to the real config and reload:

```bash
sed "s/__DOMAIN__/your-domain.com/g" nginx/app.conf > nginx/active.conf
docker compose -f docker-compose.prod.yml restart nginx
```

Visit `https://your-domain.com/` — the React admin panel's login page
should load over HTTPS.

## 7. Create the superadmin and go live

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

Log into the admin panel, then follow the **"Adding a tenant + bot"**
section in `README.md` to create your first tenant and register its real
Telegram bot — the webhook auto-registers against `PUBLIC_BASE_URL` from
`.env` (now your real domain), no extra step needed.

## 8. Certificate renewal

The `certbot` service already runs a `certbot renew` check every 12 hours
in the background — no cron needed for renewal itself. nginx, however,
only reads the certificate files at startup, so it needs a periodic reload
to pick up a renewed cert. Add one cron job on the host for that:

```bash
crontab -e
```

```
0 3 * * 0 cd /home/deploy/pharmacy-cashback && docker compose -f docker-compose.prod.yml restart nginx
```

(Weekly restart is far more often than needed — certs renew ~30 days
before expiry — but it's cheap and keeps this simple.)

## 9. Updating the deployed app

```bash
cd pharmacy-cashback
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`web`'s startup command re-runs `migrate` and `collectstatic` every time,
so new migrations apply automatically.

**If this pull touched `nginx/app.conf`, that alone is not enough** —
`nginx/active.conf` (step 6) is a one-time, gitignored, domain-substituted
copy generated from `app.conf`; `git pull` updates the template but never
regenerates the copy nginx is actually serving, so template edits silently
never take effect until you redo this:

```bash
sed "s/__DOMAIN__/your-domain.com/g" nginx/app.conf > nginx/active.conf
docker compose -f docker-compose.prod.yml exec nginx nginx -t   # validate first
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

## Backups

`scripts/backup_db.sh` dumps the `db` service with `pg_dump`, verifies the
dump (gzip integrity + a check that it's actually a pg_dump SQL stream, not
an empty/truncated file), and prunes local copies older than `KEEP_DAYS`
(14 by default). It never reads or prints `POSTGRES_PASSWORD` itself — the
dump runs entirely inside the `db` container using that container's own
environment.

**Schedule it nightly** (crontab -e, alongside the existing nginx-restart
job):

```
0 3 * * * cd /root/pharmacy-cashback && ./scripts/backup_db.sh >> /root/backups/backup-cron.log 2>&1
```

Failures exit non-zero and are logged to `$BACKUP_DIR/backup.log`
(`/root/backups/backup.log` by default) — check that log (or wire cron's
`MAILTO` / a monitoring check on the exit code) rather than assuming a
scheduled run succeeded just because it's scheduled.

**Off-box storage is still required and is NOT set up by this script.**
Everything `backup_db.sh` produces lives on the same VPS disk as `pgdata`
— a disk failure or an accidental `docker volume rm` destroys the database
*and* every backup this script has ever made in the same event. Ship
`$BACKUP_DIR` off-box on the same schedule (e.g. `rclone sync` to S3 /
Backblaze B2, or a periodic `scp`/`rsync` to a second host) — this needs
storage credentials that aren't part of this repo or this server's current
configuration, so it's a required follow-up, not optional hardening.

**Restore procedure**: `scripts/restore_db.sh /path/to/backup.sql.gz`.
It verifies gzip integrity first, then refuses to run against a database
that already has tables unless `FORCE=1` is set — a plain-SQL restore into
a live, populated database can duplicate/conflict with existing rows
rather than cleanly replace them. The intended disaster-recovery flow is:
restore into a **fresh** `db` volume/container, verify the data, then cut
the app over — not restore in place over a database still taking traffic.
Restore was verified end-to-end against a throwaway container during this
change (26/26 tables restored correctly); it has intentionally never been
run against the production database, which this procedure doesn't require
and shouldn't be used for.

**Verification cadence**: a monthly restore drill (restore the latest
nightly dump into a scratch container, confirm table counts and a few
known rows look right) is the only way to know backups are actually
restorable rather than merely present — the gzip/header check in
`backup_db.sh` catches corruption, not application-level correctness.

## Notes

- **Scaling**: see the sizing discussion in this project's chat history —
  the recommended starting VPS (2 vCPU / 4GB) comfortably covers roughly a
  dozen tenants before Postgres needs attention. Watch `docker stats` and
  the server's overall CPU/RAM under real load.
