# Production Cutover Runbook — Centralized Auth Origin + DB-Backed Access Codes

**Code state:** all changes are merged to `main` and will deploy via CI. This
runbook covers the one-time infrastructure steps a human must perform before (or
alongside) that deploy.

**Maintenance window required:** no. The auth endpoint moves atomically from a
Next.js path to a dedicated subdomain; the old path keeps working until nginx is
reloaded. The only user-visible disruption is a **forced one-time re-login** for
every session (because the cookie domain changes from `thecommons.town` to
`.thecommons.town`). With no active user base this is acceptable.

**Do not:** touch DNS CNAME records, VM firewall rules, or any production `.env`
file until you reach the step that explicitly asks for it.

---

## Phase 1 — Cloudflare DNS (2 min, do this first)

The `auth` subdomain must resolve before nginx can serve it.

1. Log in to the Cloudflare dashboard → select the `thecommons.town` zone.
2. DNS → Add record:
   - **Type:** A
   - **Name:** `auth`
   - **IPv4 address:** `129.80.229.41`
   - **Proxy status:** proxied (orange cloud)
   - TTL: Auto
3. Confirm the record appears in the list. Propagation is instant through
   Cloudflare's proxy.

> No CNAME — use an A record like the other subdomains.

---

## Phase 2 — TLS: confirm the origin cert covers `*.thecommons.town` (5 min)

The existing cert may only cover `thecommons.town` and `api.thecommons.town`. The
`auth` subdomain needs wildcard coverage or the browser gets a Cloudflare 526.

4. On the VM, check the current cert:
   ```bash
   openssl x509 -noout -text -in /etc/ssl/cloudflare/thecommons.town.pem \
     | grep -A2 "Subject Alternative Name"
   ```
   If `*.thecommons.town` appears, skip to step 7.

5. In Cloudflare → SSL/TLS → Origin Server → Create Certificate:
   - Hostnames: `thecommons.town`, `*.thecommons.town`
   - Key type: RSA (2048)
   - Validity: 15 years
   - Generate → copy the **Certificate** and **Private Key**.

6. On the VM, replace the files:
   ```bash
   sudo tee /etc/ssl/cloudflare/thecommons.town.pem <<'EOF'
   <paste certificate here>
   EOF

   sudo tee /etc/ssl/cloudflare/thecommons.town.key <<'EOF'
   <paste private key here>
   EOF

   sudo chmod 600 /etc/ssl/cloudflare/thecommons.town.key
   ```

7. Test nginx before reloading (run this even if you skipped step 5–6):
   ```bash
   sudo nginx -t
   ```
   Fix any errors before continuing.

---

## Phase 3 — nginx: add the `auth` server block (5 min)

Better Auth still runs inside Next.js on port 3000. The new block reverse-proxies
`auth.thecommons.town` to the same upstream.

8. Open the single nginx config file (one file, many server blocks — do NOT create
   a new file in `sites-available`):
   ```bash
   sudo nano /etc/nginx/sites-available/thecommons
   ```

9. Append the following server block (mirror the style of the existing
   `broadcast.thecommons.town` block):
   ```nginx
   server {
       listen 443 ssl;
       server_name auth.thecommons.town;

       ssl_certificate     /etc/ssl/cloudflare/thecommons.town.pem;
       ssl_certificate_key /etc/ssl/cloudflare/thecommons.town.key;

       location / {
           proxy_pass         http://127.0.0.1:3000;
           proxy_set_header   Host              $host;
           proxy_set_header   X-Real-IP         $remote_addr;
           proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
           proxy_set_header   X-Forwarded-Proto $scheme;
       }
   }
   ```

10. If the existing HTTP→HTTPS redirect block lists hostnames explicitly (rather
    than a wildcard `server_name`), add `auth.thecommons.town` to its `server_name`
    list now.

11. Reload nginx:
    ```bash
    sudo nginx -t && sudo systemctl reload nginx
    ```

12. Confirm the JWKS endpoint is reachable (no auth yet, just TLS + routing):
    ```bash
    curl -s https://auth.thecommons.town/api/auth/jwks
    ```
    You should see an empty `{"keys":[]}` or an error from Next.js — either way a
    200/4xx from the app (not a Cloudflare 526) means the proxy is working.

---

## Phase 4 — VM env edits (10 min)

Edit these files directly on the VM. The CI deploy that follows will read the new
values on restart.

### theCommonsWeb — `/home/ubuntu/thecommons/theCommonsWeb/.env.local`

13. Set or update these three values:
    ```
    BETTER_AUTH_URL=https://auth.thecommons.town
    NEXT_PUBLIC_BETTER_AUTH_URL=https://auth.thecommons.town
    BETTER_AUTH_COOKIE_DOMAIN=.thecommons.town
    ```
    > Setting `BETTER_AUTH_COOKIE_DOMAIN` activates `crossSubDomainCookies` and
    > `SameSite=None; Secure` in `theCommonsWeb/src/lib/auth.ts`. All existing
    > sessions become invalid — every user is forced to re-login once.

### backendServer — `/home/ubuntu/thecommons/backendServer/.env`

14. Update the JWKS URL (was `https://thecommons.town/api/auth/jwks`) **and the
    issuer** — tokens minted after the cutover carry
    `iss=https://auth.thecommons.town` (the new `BETTER_AUTH_URL`), and
    `backend/jwt_auth.py` rejects any JWT whose `iss` doesn't match
    `BETTER_AUTH_ISSUER`, so skipping this breaks all API auth:
    ```
    BETTER_AUTH_JWKS_URL=https://auth.thecommons.town/api/auth/jwks
    BETTER_AUTH_ISSUER=https://auth.thecommons.town
    ```
    (`BETTER_AUTH_AUDIENCE`, if set, keeps its current value — the audience is
    the app, not the auth origin.)

15. Ensure `CORS_EXTRA_ORIGINS` includes `https://broadcast.thecommons.town` (it
    should already be there from the broadcast cutover; verify it):
    ```
    CORS_EXTRA_ORIGINS=https://thecommons.town,https://broadcast.thecommons.town
    ```

16. Remove the now-dead env var (codes live in SQL; this line is ignored by code
    but remove it to avoid confusion):
    ```
    # DELETE this line entirely:
    BROADCAST_ACCESS_CODES=...
    ```

### broadcastWeb — `/home/ubuntu/thecommons/broadcastWeb/.env`

17. Set the auth URL:
    ```
    VITE_BETTER_AUTH_URL=https://auth.thecommons.town
    ```

---

## Phase 5 — Deploy and migrate (CI-driven, ~10 min)

The CI workflow runs on every push to `main`. If the code is already merged:

18. Trigger a deploy by pushing any no-op commit, or re-run the latest CI workflow
    from the GitHub Actions tab.

    Alternatively, run the manual fallback sequence on the VM:
    ```bash
    cd /home/ubuntu/thecommons && git pull

    # Backend
    cd backendServer
    /snap/bin/uv sync
    /snap/bin/uv run python manage.py migrate        # applies broadcast 0005
    /snap/bin/uv run python manage.py collectstatic --noinput

    # theCommonsWeb (picks up new env values)
    cd ../theCommonsWeb && pnpm install && pnpm run build

    # broadcastWeb (picks up VITE_BETTER_AUTH_URL)
    cd ../broadcastWeb && pnpm install && pnpm run build
    ```

19. Confirm migration 0005 ran (creates `AccessCode`, `BroadcastAccess`,
    `AccessCodeUse` tables):
    ```bash
    cd /home/ubuntu/thecommons/backendServer
    /snap/bin/uv run python manage.py showmigrations broadcast
    ```
    All lines should show `[X]`.

    > **ingestion note:** migration 0008 was deleted before it ever shipped to
    > prod. No ingestion migration action is needed on the production DB.

---

## Phase 6 — Restart services (2 min)

20. Restart Next.js so it loads the new `BETTER_AUTH_*` env values:
    ```bash
    sudo systemctl restart nextjs
    ```

21. Restart gunicorn so Django picks up the new `BETTER_AUTH_JWKS_URL`:
    ```bash
    sudo systemctl restart gunicorn
    ```

22. Verify all services came back:
    ```bash
    sudo systemctl status nextjs gunicorn celery celerybeat broadcast-worker redis-server
    ```
    All should show `active (running)`.

---

## Phase 7 — Mint replacement access codes (5 min per operator)

The `BROADCAST_ACCESS_CODES` env var is gone. Issue a DB-backed code for each
operator. The raw code prints exactly once; copy it immediately and deliver it to
the operator via a secure channel.

23. SSH into the VM:
    ```bash
    ssh -i oraclevps.key ubuntu@129.80.229.41
    cd /home/ubuntu/thecommons/backendServer
    ```

24. Generate a code for each operator. Common invocations:
    ```bash
    # Tier-2 operator, 3 uses (default)
    /snap/bin/uv run python manage.py generate_access_code \
      --tier 2 --label "<operator-label>"

    # Tier-2 operator, unlimited uses
    /snap/bin/uv run python manage.py generate_access_code \
      --tier 2 --unlimited --label "<operator-label>"

    # Tier-1 trial code, 5 uses
    /snap/bin/uv run python manage.py generate_access_code \
      --tier 1 --uses 5 --label "<operator-label>"
    ```
    The command prints:
    ```
    ACCESS CODE (copy now):
      <raw-code>
    Store it now — it will not be shown again.
    ```
    **Copy `<raw-code>` now.** It is not stored; only the hash is saved.

25. Deliver each raw code to its operator via a secure channel (1Password share,
    Signal, etc.). Do not send codes in email or chat.

26. Confirm all codes appear in the DB:
    ```bash
    /snap/bin/uv run python manage.py list_access_codes
    ```

---

## Phase 8 — Smoke tests (5 min)

Run these in order. All should pass before you close the runbook.

27. **Auth origin reachable:**
    ```bash
    curl -s https://auth.thecommons.town/api/auth/jwks | python3 -m json.tool
    ```
    Expected: JSON object with a `"keys"` array (may be empty on a fresh DB, but
    must be valid JSON with a 200 response).

28. **Main site login:**
    Open `https://www.thecommons.town` in an incognito window. Log in with a test
    account. Confirm you land on the authenticated view. The session cookie should
    now have `Domain=.thecommons.town`.

29. **Broadcast access endpoint (Bearer token path):**
    In the browser, navigate to `https://broadcast.thecommons.town`. Sign in.
    Open DevTools → Console and run:
    ```js
    fetch('https://api.thecommons.town/broadcast/access', {
      headers: { Authorization: 'Bearer ' + await (await fetch('/api/auth/get-session')).json().token }
    }).then(r => r.json()).then(console.log)
    ```
    Expected: `{ "tier": <N>, ... }` (not a 401 or 403).

30. **Access-code path (trial code):**
    From the browser or curl, send a generated code as a header:
    ```bash
    curl -s -H "X-Broadcast-Access-Code: <raw-code>" \
      https://api.thecommons.town/broadcast/access
    ```
    Expected: `{ "tier": <N>, "is_trial": true, ... }` with HTTP 200.

31. **AI-autofill gate:**
    Make an authenticated request to the autofill endpoint as a tier-1 user.
    Expected: HTTP 403 (tier 2 required). Confirm a tier-2 session gets 200.

32. **Healthcheck:**
    ```bash
    cd /home/ubuntu/thecommons
    UV_BIN=/snap/bin/uv bash deploy/healthcheck.sh
    ```
    All lines should show checkmarks. Any critical failure (`✗`) must be resolved
    before declaring the cutover complete.

---

## Phase 9 — Rollback procedure

If something is badly wrong and you need to revert the auth origin change:

33. On the VM, revert the three auth env vars in `theCommonsWeb/.env.local`:
    ```
    BETTER_AUTH_URL=https://thecommons.town
    NEXT_PUBLIC_BETTER_AUTH_URL=https://thecommons.town
    # Remove or comment out:
    # BETTER_AUTH_COOKIE_DOMAIN=.thecommons.town
    ```

34. Revert the JWKS URL and issuer in `backendServer/.env`:
    ```
    BETTER_AUTH_JWKS_URL=https://thecommons.town/api/auth/jwks
    BETTER_AUTH_ISSUER=https://thecommons.town
    ```

35. Revert the broadcastWeb build env in `broadcastWeb/.env`:
    ```
    VITE_BETTER_AUTH_URL=https://thecommons.town
    ```

36. Rebuild the frontends and restart:
    ```bash
    cd /home/ubuntu/thecommons/theCommonsWeb && pnpm run build && sudo systemctl restart nextjs
    cd ../broadcastWeb && pnpm run build
    sudo systemctl restart gunicorn
    ```

37. The `auth.thecommons.town` DNS record and nginx server block can stay in
    place — they will simply be unused until the cutover is re-attempted.

> **Access codes cannot roll back to env.** The `BROADCAST_ACCESS_CODES` code
> path is removed. If you roll back the auth origin, DB-backed codes (`AccessCode`
> table) continue to work as long as gunicorn is running the post-merge code. If
> you also need to roll back to a pre-merge binary, you must reissue codes via
> whatever mechanism the older code supported.

---

## Quick-reference — access code management commands

```bash
# Mint a new code (raw printed once)
/snap/bin/uv run python manage.py generate_access_code \
  --label "<label>" [--tier 2] [--uses N | --unlimited] [--expires ISO8601]

# List all codes (no raw codes shown)
/snap/bin/uv run python manage.py list_access_codes

# Revoke a code by label or DB id
/snap/bin/uv run python manage.py revoke_access_code <label-or-id>

# Set a user's broadcast access tier directly (0 = none, 1 = trial, 2 = full)
/snap/bin/uv run python manage.py set_broadcast_access <email> <0|1|2>
```

---

## Execution record — 2026-07-30 (ticket 37.9)

Cutover executed on prod (Oracle VM `129.80.229.41`). Phases 1–8 run in order.

| Phase | Action | Result |
|-------|--------|--------|
| 1 | Cloudflare A record `auth` → `129.80.229.41` (proxied) | done |
| 2 | Origin cert wildcard `*.thecommons.town` | confirmed/covered |
| 3 | nginx `auth.thecommons.town` server block → `127.0.0.1:3000`; `nginx -t` + reload | done; `curl auth.thecommons.town/api/auth/jwks` → 200 |
| 4 | env already pointed at `auth.thecommons.town` in all three files; only edit was deleting the dead `BROADCAST_ACCESS_CODES` line from `backendServer/.env` (backup `.env.bak-precutover-37.9`). `DJANGO_ENV=prod` confirmed present. | done |
| 5 | `git pull` (already at `58332f4`); `uv sync`; `migrate` (no-op, broadcast 0001–0010 all `[X]`); `collectstatic`; `pnpm build` both frontends (exit 0) | done |
| 6 | `systemctl restart nextjs gunicorn`; all 7 services + 3 workers active | done |
| 7 | minted tier-1/tier-2/trial verification codes, then **revoked** them (ids 30–32) after testing | done |
| 8 | smoke tests (below) | all pass |

**Phase-8 verification results:**

- **JWKS (criterion 1):** `https://auth.thecommons.town/api/auth/jwks` → 200, valid JSON, EdDSA key `kid=8746d8a9…`.
- **Live JWT verifies Django-side (criteria 2–3):** portal login mints a JWT with
  `iss=aud=https://auth.thecommons.town`; `/api/auth/token` mints the **new** issuer.
  From `broadcast.thecommons.town` (CORS-allowed origin), a live Bearer call to
  `GET /broadcast/access` → **200 `{tier:2, is_trial:false}`** (not 401/403). Redeeming an
  UPGRADE code (`RequiresBroadcastLogin`) succeeded — both require Django to verify the JWT.
  > Note: `inspect_broadcast_jwt` was **not** run — the browser-automation harness blocks
  > raw-token exfiltration. The live authenticated API calls are a stronger equivalent proof.
- **Cross-subdomain session (criterion 3):** after a single portal login, `broadcast.thecommons.town`
  showed "✓ signed in" via the shared `.thecommons.town` cookie.
- **Tier gate:** tier-0 and tier-1 → AI-autofill UI locked / endpoint denied; tier-2 →
  `POST /broadcast/ai-autofill` **200** with live Gemini extraction.
- **Healthcheck (criterion 4):** `deploy/healthcheck.sh` → all checks passed.

### Gotcha found during verification — stale cached 301 (browser-local, NOT a prod defect)

A browser used during the mid-July 2026 touchup window had a **permanently-cached
`301 Moved Permanently`** for `auth.thecommons.town/api/auth/*` → `thecommons.town/api/auth/*`
(cached `Date: Tue, 14 Jul 2026`). After the cutover, that stale 301 redirected the
same-origin auth calls cross-origin, which then CORS-failed (`Failed to fetch`) and blocked
account creation / `get-session` in **that browser only**. Server-side there is no redirect
(`curl` → 200). Fix for an affected browser: hard-clear cache / "Disable cache" in DevTools,
or a `cache:'reload'` fetch to evict the entry. New visitors with a clean cache are unaffected.
