# VM Deployment — The Commons

This document describes the production setup on the Oracle Cloud VM. Read this before making any changes to services, nginx config, or deployment scripts.

---

## VM Specs

- **Provider:** Oracle Cloud Infrastructure (OCI)
- **OS:** Ubuntu 24.04, ARM64 (aarch64)
- **IP:** `129.80.229.41`
- **SSH:** `ssh -i oraclevps.key ubuntu@129.80.229.41` (key is in repo root, never commit it)

---

## DNS & TLS

- DNS is managed through **Cloudflare**, proxied (orange cloud).
- SSL/TLS mode: **Full (strict)**.
- Origin cert (Cloudflare-issued) lives on the VM at:
  - `/etc/ssl/cloudflare/thecommons.town.pem`
  - `/etc/ssl/cloudflare/thecommons.town.key`
- DNS records:
  - `thecommons.town` A → `129.80.229.41`
  - `api.thecommons.town` A → `129.80.229.41`

---

## File Layout on the VM

```
/home/ubuntu/thecommons/
├── backendServer/          # Django app
│   ├── .env                # Backend secrets (not in git)
│   ├── .venv/              # uv-managed virtualenv
│   ├── backend/            # Django project (settings, wsgi, urls)
│   ├── events/             # Events app
│   ├── ingestion/          # Ingestion pipeline app
│   ├── staticfiles/        # Output of collectstatic (served by nginx at /static/)
│   └── manage.py
└── theCommonsWeb/          # Next.js app
    ├── .env.local          # Frontend secrets (not in git)
    ├── .next/              # Build output
    └── src/

/etc/nginx/sites-available/thecommons   # nginx config
/etc/systemd/system/gunicorn.service    # gunicorn service
/etc/systemd/system/nextjs.service      # Next.js service
/etc/ssl/cloudflare/                    # TLS certs
/run/gunicorn/gunicorn.sock             # Unix socket (created at runtime by systemd)
```

---

## Services

### gunicorn (Django backend)

- **Socket:** `unix:/run/gunicorn/gunicorn.sock`
- **Workers:** 3 sync workers
- **Service file:** `/etc/systemd/system/gunicorn.service`
- The `RuntimeDirectory=gunicorn` directive in the service file tells systemd to create `/run/gunicorn/` owned by `ubuntu` before starting — this is required because `ubuntu` can't write to `/run/` directly.

```
sudo systemctl status gunicorn
sudo systemctl restart gunicorn
sudo journalctl -u gunicorn -n 50
```

### nextjs (Next.js frontend)

- **Port:** `3000`
- **Service file:** `/etc/systemd/system/nextjs.service`
- Runs `npm run start` (calls `next start`) from `/home/ubuntu/thecommons/theCommonsWeb/`

```
sudo systemctl status nextjs
sudo systemctl restart nextjs
sudo journalctl -u nextjs -n 50
```

### nginx

- **Config:** `/etc/nginx/sites-available/thecommons` (symlinked into `sites-enabled/`)
- Routes:
  - `thecommons.town` → proxy to `http://localhost:3000` (Next.js)
  - `api.thecommons.town` → proxy to `unix:/run/gunicorn/gunicorn.sock` (Django)
  - `www.thecommons.town` → 301 to `thecommons.town`
  - HTTP (port 80) → 301 to HTTPS
  - `api.thecommons.town/static/` → alias to `backendServer/staticfiles/` (Django admin CSS)

```
sudo nginx -t
sudo systemctl reload nginx
sudo tail -50 /var/log/nginx/access.log
sudo tail -20 /var/log/nginx/error.log
```

---

## Package Managers

- **Python:** `uv` (installed via `sudo snap install astral-uv --classic`). Never use `pip` directly. Use `uv sync` to install deps and `uv run python manage.py ...` to run management commands.
- **Node:** `pnpm` (installed via `sudo npm install -g pnpm`). Never use `npm install` — it re-resolves deps and breaks peer dependency pinning. Use `pnpm install` and `pnpm run build`.

---

## Deploying Updates

### Backend changes

```bash
cd /home/ubuntu/thecommons
git pull
cd backendServer
uv sync                                      # only needed if pyproject.toml changed
uv run python manage.py migrate              # only needed if models changed
uv run python manage.py collectstatic --noinput   # only needed if static files changed
sudo systemctl restart gunicorn
```

### Frontend changes

```bash
cd /home/ubuntu/thecommons
git pull
cd theCommonsWeb
pnpm install     # only needed if pnpm-lock.yaml changed
pnpm run build
sudo systemctl restart nextjs
```

---

## Environment Variables

### `backendServer/.env`

```
DATABASE_URL=               # Neon Postgres connection string
DJANGO_SECRET_KEY=
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,api.thecommons.town
CORS_EXTRA_ORIGINS=https://thecommons.town
CSRF_TRUSTED_ORIGINS=https://api.thecommons.town,https://thecommons.town
GEMINI_API_KEY=
CRON_SECRET=
THE_COMMONS_API_KEY=
BETTER_AUTH_JWKS_URL=https://thecommons.town/api/auth/jwks
BETTER_AUTH_ISSUER=https://thecommons.town
BETTER_AUTH_AUDIENCE=
BREVO_API_KEY=
DIGEST_FROM_EMAIL=digest@thecommons.town
SITE_URL=https://thecommons.town
```

### `theCommonsWeb/.env.local`

```
NEXT_PUBLIC_API_BASE_URL=https://api.thecommons.town
NEXT_PUBLIC_THE_COMMONS_API_KEY=
DATABASE_URL=               # Same Neon connection string
BETTER_AUTH_SECRET=
BETTER_AUTH_URL=https://thecommons.town
NEXT_PUBLIC_BETTER_AUTH_URL=https://thecommons.town
```

---

## Broadcast (event syndication) — additional setup

The broadcast feature adds a third subdomain, a systemd worker, and Playwright.
Templates live in `deploy/` in the repo.

### One-time prerequisites (in order)

1. **TLS (prerequisite, not a verify-step):** the existing origin cert covers
   only `thecommons.town` and `api.thecommons.town`. In the Cloudflare
   dashboard, reissue an origin cert for `thecommons.town, *.thecommons.town`,
   replace `/etc/ssl/cloudflare/thecommons.town.{pem,key}`, then
   `sudo nginx -t && sudo systemctl reload nginx`. Skipping this makes the
   subdomain fail with a 526 SSL error at Cloudflare.
2. **Cloudflare DNS:** add an **A record** `broadcast` → `129.80.229.41`,
   proxied (orange cloud) — A record like the others, not a CNAME.
3. **Playwright Chromium (bundled only — never "chrome"; arm64 has no branded
   Chrome):**
   ```bash
   cd /home/ubuntu/thecommons/backendServer
   uv run playwright install chromium          # → /home/ubuntu/.cache/ms-playwright/
   uv run playwright install-deps chromium     # apt system libs (needs sudo)
   ```
4. **Artifact dirs:** `mkdir -p /home/ubuntu/broadcast/{screenshots,downloads}`
5. **Env:** add the `BROADCAST_*` block (see `backendServer/.env.example`) to
   `backendServer/.env`; append `https://broadcast.thecommons.town` to
   `CORS_EXTRA_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.
6. **Worker service:** copy `deploy/broadcast-worker.service` to
   `/etc/systemd/system/`, then
   `sudo systemctl daemon-reload && sudo systemctl enable --now broadcast-worker`.
7. **nginx:** add the server block from `deploy/nginx-broadcast.conf.snippet`
   to the existing `/etc/nginx/sites-available/thecommons` (one file, many
   blocks — do not create a new sites-available file).

### Deploying broadcast updates

```bash
cd /home/ubuntu/thecommons && git pull
cd backendServer
uv sync                                       # if pyproject.toml changed
uv run python manage.py migrate               # broadcast migrations
sudo systemctl restart gunicorn
sudo systemctl restart broadcast-worker

# Broadcast SPA (static — no service to restart; pnpm only, never npm)
cd ../broadcastWeb
pnpm install                                  # if pnpm-lock.yaml changed
pnpm run build                                # → dist/, served directly by nginx
```

```
sudo systemctl status broadcast-worker
sudo journalctl -u broadcast-worker -n 50
```

If `curl https://broadcast.thecommons.town/` hangs after setup, it's the
iptables REJECT-before-ACCEPT gotcha below (same 80/443, no new rules needed).

---

## Firewall

Two layers — both must allow 80/443:

1. **Oracle VCN Security List** — configured in OCI console. Ports 22, 80, 443 are open via ingress rules.
2. **iptables on the VM** — Oracle Ubuntu images ship with a catch-all `REJECT` rule. The ACCEPT rules for 80/443 must appear **before** that rule in the INPUT chain (position 5, not appended). Check with:

```bash
sudo iptables -L INPUT -n --line-numbers
```

The ACCEPT rules for ports 80 and 443 should have lower line numbers than the REJECT rule. If they don't, insert them at position 5:

```bash
sudo iptables -I INPUT 5 -p tcp --dport 443 -m state --state NEW -j ACCEPT
sudo iptables -I INPUT 5 -p tcp --dport 80 -m state --state NEW -j ACCEPT
```

These rules are not automatically persisted across reboots — save them with:

```bash
sudo netfilter-persistent save
```

---

## Troubleshooting

| Symptom | Likely cause | Check |
|---------|-------------|-------|
| `curl` to IP returns nothing | iptables REJECT before ACCEPT | `sudo iptables -L INPUT -n --line-numbers` |
| nginx 502 Bad Gateway | gunicorn or nextjs down | `sudo systemctl status gunicorn nextjs` |
| Django `DisallowedHost` | `api.thecommons.town` missing from `ALLOWED_HOSTS` | `backendServer/.env` → `DJANGO_ALLOWED_HOSTS` |
| 400 on `/events/` from browser | `NEXT_PUBLIC_API_BASE_URL` wrong or build stale | Check `.env.local`, rebuild with `pnpm run build` |
| gunicorn socket permission denied | Socket path outside `RuntimeDirectory` | Verify `ExecStart` uses `unix:/run/gunicorn/gunicorn.sock` |
| Django admin has no CSS | `collectstatic` not run or nginx `/static/` alias wrong | `uv run python manage.py collectstatic --noinput` |
