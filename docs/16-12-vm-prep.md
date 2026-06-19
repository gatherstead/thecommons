# 16.12 / 16.13 — VM SSH deploy prep + GitHub secrets (runbook)

> Transient. The agent can't SSH in, so this is a paste-and-run checklist for the
> operator. Delete this file once the dry-run (last section) succeeds and the four
> GitHub secrets exist. Source of truth for the deploy sequence is `DEPLOY.md`.

**Goal:** get the Oracle VM to the point where a single non-interactive SSH command
can run `git pull → uv sync → migrate → collectstatic → pnpm install → pnpm build`
and restart every unit (gunicorn, nextjs, celery, celerybeat, broadcast-worker),
authenticated by a dedicated ed25519 key that GitHub Actions will hold.

Legend: 🖥️ = run on your **local** machine · ☁️ = run **on the VM** (`./ssh.sh`).

---

## 16.12 — VM prep

### 1. Decide the deploy user — reuse `ubuntu`

Reuse the existing `ubuntu` user. All systemd units (`gunicorn`, `nextjs`,
`celery`, `celerybeat`, `broadcast-worker`) run as `ubuntu`, the repo lives in
`/home/ubuntu/thecommons`, and `.env` is owned by `ubuntu` — a dedicated deploy
user would need group membership, file-ownership changes, and its own sudoers
entry for no real isolation gain on a single-tenant box.

> **Security trade-off (accept knowingly):** `ubuntu` is the box's primary sudoer.
> The deploy key we add below can therefore run *anything the deploy command runs*
> as `ubuntu`, and (via the scoped sudoers drop-in in step 3) restart five units
> without a password. We mitigate by (a) scoping the NOPASSWD grant to exactly
> those five `systemctl restart` calls — not blanket NOPASSWD, and (b) keeping the
> private key only in GitHub Actions secrets (never on a laptop, never in chat).
> If this repo ever goes multi-tenant or public-contributor, revisit with a
> locked-down dedicated `deploy` user.

### 2. Generate a dedicated deploy keypair (🖥️ local)

Do **not** reuse `oraclevps.key`. Make a fresh key whose only job is CI deploys, so
it can be rotated/revoked independently.

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy@thecommons" -f ~/.ssh/thecommons_deploy -N ""
```

This produces:
- `~/.ssh/thecommons_deploy`      → **private** key (PEM). Goes into GitHub secret `ORACLE_SSH_KEY` in 16.13. **Never paste it into chat, commit it, or store it on the VM.**
- `~/.ssh/thecommons_deploy.pub`  → **public** key. Goes on the VM in the next step.

Add the **public** key to the VM (run from local; uses your existing key to log in):

```bash
ssh-copy-id -i ~/.ssh/thecommons_deploy.pub -o IdentityFile=oraclevps.key ubuntu@129.80.229.41
```

If `ssh-copy-id` isn't available, append it manually:

```bash
cat ~/.ssh/thecommons_deploy.pub | ssh -i oraclevps.key ubuntu@129.80.229.41 \
  'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

Verify the new key logs in **before** going further:

```bash
ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 'echo deploy-key-ok'
# → deploy-key-ok
```

### 3. Scoped sudoers drop-in (☁️ VM)

Grant `ubuntu` passwordless `systemctl restart` for **only** the five deploy units
— not blanket NOPASSWD. `visudo` validates syntax so a typo can't lock you out.

```bash
sudo visudo -f /etc/sudoers.d/deploy-restart
```

Paste exactly (note the explicit unit list — no wildcards):

```sudoers
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart gunicorn, \
                            /usr/bin/systemctl restart nextjs, \
                            /usr/bin/systemctl restart celery, \
                            /usr/bin/systemctl restart celerybeat, \
                            /usr/bin/systemctl restart broadcast-worker
```

> Confirm the systemctl path first with `command -v systemctl` (usually
> `/usr/bin/systemctl` on Ubuntu 24.04). The path in sudoers must match exactly or
> the NOPASSWD rule won't apply.

Verify the grant works without a password and is correctly scoped:

```bash
sudo -n systemctl restart gunicorn && echo "restart OK (no password)"
sudo -n systemctl restart redis-server 2>&1 | grep -q password && echo "redis correctly NOT granted"
```

### 4. Confirm `git pull origin main` is non-interactive (☁️ VM)

A CI deploy must never block on a username/password or host-key prompt.

```bash
cd /home/ubuntu/thecommons
git remote -v
git pull origin main          # must complete with NO credential prompt
```

If it prompts:
- **HTTPS remote** → either switch to SSH (`git remote set-url origin git@github.com:<org>/<repo>.git` + add a deploy key to the repo) or store a PAT via `git config --global credential.helper store` (one-time `git pull` to cache it). SSH deploy key is cleaner.
- **First-time GitHub host key** → pre-seed it so the pull never asks:
  ```bash
  ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
  ```

### 5. Confirm `uv` + `pnpm` on PATH for **non-interactive** shells (☁️ VM)

This is the classic CI footgun. `ssh host 'cmd'` runs a **non-interactive,
non-login** shell; Ubuntu's default `~/.bashrc` returns early in that case, so any
PATH set there is ignored. Check what a CI shell actually sees:

```bash
ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 'echo PATH=$PATH; command -v uv; command -v pnpm; command -v node'
```

If `uv`/`pnpm`/`node` are **not** found, pick one fix:

- **(Recommended) Use absolute paths in the deploy command.** Capture them once:
  ```bash
  ssh ... 'which uv pnpm node'   # e.g. /snap/bin/uv  /usr/bin/pnpm  /usr/bin/node
  ```
  `uv` is `/snap/bin/uv` (snap install); the systemd units already hardcode this.
  Use these absolute paths in the deploy pipeline (step 7) and the GitHub workflow.
- **Or** export PATH at the *top* of `~/.profile` (before any interactivity guard):
  ```bash
  echo 'export PATH="/snap/bin:$HOME/.local/bin:$PATH"' >> ~/.profile
  ```
  …and invoke the deploy over `ssh -t` / a login shell so `.profile` is sourced.
  Absolute paths are less fragile — prefer them.

### 6. Confirm Redis + Celery/beat units installed & enabled (☁️ VM)

The deploy restarts celery/celerybeat/broadcast-worker, which require Redis up and
the units installed. (First-time install steps are in `DEPLOY.md` §Services.)

```bash
# Redis broker/cache — must be active AND enabled (survives reboot)
systemctl is-active redis-server && systemctl is-enabled redis-server
redis-cli -a "$(grep -oP 'REDIS_URL=redis://:\K[^@]+' backendServer/.env)" PING   # → PONG

# All five deploy units exist, are enabled, and currently active
systemctl is-enabled gunicorn nextjs celery celerybeat broadcast-worker
systemctl is-active  gunicorn nextjs celery celerybeat broadcast-worker
```

If any unit is missing/disabled, install it from `deploy/*.service` per `DEPLOY.md`
(celery/celerybeat §Services; broadcast-worker §Broadcast) and
`sudo systemctl enable --now <unit>` before continuing.

### 7. Staged manual dry-run of the full pipeline (☁️ VM)

Run the complete sequence **by hand** once, exactly as CI will, and capture output.
Use the absolute paths confirmed in step 5 (shown here as `/snap/bin/uv` and
`pnpm`; substitute what `which` reported).

```bash
set -euo pipefail
cd /home/ubuntu/thecommons
git pull origin main

cd backendServer
/snap/bin/uv sync
/snap/bin/uv run python manage.py migrate --noinput
/snap/bin/uv run python manage.py collectstatic --noinput

cd ../theCommonsWeb
pnpm install --frozen-lockfile
pnpm run build

cd ../broadcastWeb
pnpm install --frozen-lockfile
pnpm run build

# Restart every unit (NOPASSWD via the step-3 drop-in)
sudo -n systemctl restart gunicorn nextjs celery celerybeat broadcast-worker

# Post-restart sanity
systemctl is-active gunicorn nextjs celery celerybeat broadcast-worker
```

Capture it for review:

```bash
bash -c '<the block above>' 2>&1 | tee ~/deploy-dryrun.log
```

**Note anything that needed fixing** (missing PATH entry, credential prompt, a unit
that didn't come back, a frozen-lockfile mismatch) and resolve it here — CI has no
human to intervene. The same `sudo -n systemctl restart …` must succeed without a
password prompt.

> `broadcastWeb` and `theCommonsWeb` both build to static/`.next`; only `nextjs`
> serves a long-running process (the broadcast SPA is served by nginx from `dist/`).
> The broadcast **worker** restart picks up backend task-code changes.

---

## 16.13 — GitHub repo secrets (checklist)

Depends on 16.12 (needs the private key + known-hosts from above).

In GitHub → **Settings → Secrets and variables → Actions → New repository secret**,
add these four:

- [ ] **`ORACLE_SSH_KEY`** — the full PEM **private** key from 16.12 step 2.
  ```bash
  cat ~/.ssh/thecommons_deploy   # 🖥️ copy ALL of it, incl. BEGIN/END lines
  ```
  Paste the entire block including `-----BEGIN OPENSSH PRIVATE KEY-----` /
  `-----END …-----`. **Never** echo this into chat or commit it.

- [ ] **`ORACLE_HOST`** — `129.80.229.41`
  Use the **raw IP**, not `api.thecommons.town`/`broadcast.thecommons.town` — those
  resolve to Cloudflare's proxy (orange cloud), which doesn't forward port 22, so
  SSH to the hostname will hang.

- [ ] **`ORACLE_USER`** — `ubuntu` (the user chosen in 16.12 step 1).

- [ ] **`ORACLE_KNOWN_HOSTS`** — output of:
  ```bash
  ssh-keyscan -t ed25519 129.80.229.41   # 🖥️ paste full line(s) into the secret
  ```
  The workflow writes this to `~/.ssh/known_hosts` so it can verify the VM's
  fingerprint instead of disabling `StrictHostKeyChecking` (which would defeat the
  point of pinning a deploy key).

### Acceptance

- [ ] All four secrets exist under repo Actions secrets.
- [ ] Secrets are **not** exposed to fork PRs. **Future-proofing:** if this repo
      ever goes public, the deploy workflow must trigger on **push-to-main only**,
      never `pull_request` — GitHub never injects repo secrets into workflows run
      from fork PRs, but a `pull_request_target` or careless trigger could leak
      them. Keep the deploy job `on: push: branches: [main]`.
- [ ] `ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 '<full pipeline>'`
      from 16.12 step 7 succeeds end-to-end with the new key and restarts all units.

---

## Done?

When the dry-run log is clean and the four secrets exist, this file has served its
purpose — delete `docs/16-12-vm-prep.md`. The reusable knowledge already lives in
`DEPLOY.md`; 16.14 wires the actual GitHub Actions workflow that runs this pipeline.
