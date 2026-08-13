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
```

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

## Notes

- **Backups**: nothing here backs up the `pgdata` volume automatically.
  At minimum, cron a nightly `docker compose -f docker-compose.prod.yml
  exec -T db pg_dump -U pharmacy pharmacy_cashback | gzip > backup-$(date
  +%F).sql.gz` off-box (e.g. to object storage) before relying on this in
  production.
- **Scaling**: see the sizing discussion in this project's chat history —
  the recommended starting VPS (2 vCPU / 4GB) comfortably covers roughly a
  dozen tenants before Postgres needs attention. Watch `docker stats` and
  the server's overall CPU/RAM under real load.
