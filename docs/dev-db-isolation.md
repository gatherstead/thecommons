# Dev DB Isolation — Design Doc

## Problem

Right now, dev and prod share the same Neon database. Both the frontend (Next.js/Drizzle, owns `neon_auth` schema) and the backend (Django, owns `public` schema) read from a single `DATABASE_URL`. There is no environment separation at the DB layer — running locally means writing to the real database.

Consequences:
- `seed_dev` seeds fake events into prod data
- Auth signups during local dev create real user rows
- There's no safe place to test schema migrations before deploying
- Accidental writes (e.g. a POST from `localhost:3000`) silently hit prod

---

## Proposed Fix: Neon Dev Branch

Neon supports branching — a branch is a copy-on-write snapshot of the DB at a point in time. It gets its own connection string, diverges independently, and can be reset or dropped freely.

**Create one branch for dev, keep the main DB for prod.**

```
Main DB (prod)       →  DATABASE_URL in prod VM .env
Dev branch of main   →  DATABASE_URL in local .env (both frontend + backend)
```

This is the right primitive here: you get the same schema and a realistic data snapshot, without ever touching prod rows.

---

## What Changes

### 1. Neon setup (one-time)

1. Go to console.neon.tech → your project → **Branches** → **Create branch**
2. Name it `dev` (or `arya-dev`, etc.)
3. Copy the connection string — it looks identical to prod's but has a different branch ID in the hostname

### 2. Local `.env` files

Both files need to point at the dev branch. They're kept in sync manually (same DB, different consumers).

**`backendServer/.env`**
```
DATABASE_URL=postgresql://...@<dev-branch-host>/neondb?sslmode=require
```

**`theCommonsWeb/.env.local`** (not `.env` — that file is a stale Vite-era leftover with `VITE_*` vars; Next.js gives `.env.local` precedence, so this is where `DATABASE_URL` actually lives)
```
DATABASE_URL=postgresql://...@<dev-branch-host>/neondb?sslmode=require
```

The prod VM's `.env` keeps its existing connection string — no change needed there. Settings selection is driven by `DJANGO_ENV` (`backend/settings/__init__.py`): the VM sets `DJANGO_ENV=prod`, local machines default to `dev`.

### 3. `seed_dev` becomes useful

Once dev has its own branch, `python manage.py seed_dev` does what it's supposed to: populates a clean local dataset without touching prod. Run it once after branching. It's idempotent (`get_or_create` everywhere), so re-running is safe.

```bash
cd backendServer
python manage.py migrate       # run against dev branch
python manage.py seed_dev      # safe — isolated branch
```

### 4. Code changes (guardrails)

`settings/dev.py` and the frontend `db.ts` already read `DATABASE_URL` from the environment, so swapping the connection string is the main change. Two small guards back it up:

- `settings/dev.py` fails fast at startup if `DATABASE_URL` is unset, instead of dying later with a confusing connection error.
- `seed_dev` refuses to run when `DEBUG` is off (i.e. prod settings). Override with `--force` if you genuinely need to seed a non-debug environment.

---

## On Dual Connection Strings

The idea of keeping both `DATABASE_URL` (dev) and `DATABASE_URL_PROD` (prod) in the same `.env` is worth considering for one specific use case: running migrations against prod from your local machine before a deploy. Outside of that, it's a footgun — any script that accidentally reads the wrong variable writes to prod silently.

**Recommendation:** don't put both in the same `.env`. Instead:
- Local `.env` → dev branch only
- Prod VM `.env` → prod DB only
- If you need to run a prod migration locally, pass it explicitly: `DATABASE_URL=<prod-url> python manage.py migrate`

---

## Migration Workflow Going Forward

```
1. Make model changes locally
2. python manage.py makemigrations
3. python manage.py migrate          ← runs against dev branch, safe to iterate
4. Verify behavior locally
5. Deploy to VM → python manage.py migrate on prod
```

---

## Checklist

- [ ] Create `dev` branch on Neon console
- [ ] Set dev branch `DATABASE_URL` in `backendServer/.env`
- [ ] Set dev branch `DATABASE_URL` in `theCommonsWeb/.env.local`
- [ ] Run `python manage.py migrate` against dev branch
- [ ] Run `python manage.py seed_dev`
- [ ] Verify frontend auth signup creates a row in the dev branch, not prod

---

## Monitoring Prod Read-Only from Local Dev

`backend/settings/dev.py:39-52` defines an optional second DB alias, `prod_readonly`, populated from `PROD_DATABASE_URL` when that env var is set. This exists so local devtools (e.g. an "Ingestion & Broadcast Monitor" page, selected via a `?db=prod_readonly` query param) can inspect real prod data — sources, ingestion runs, broadcast queue state — without routing writes through it and without merging prod into the `default` dev-branch alias above.

This only works safely if the credentials behind `PROD_DATABASE_URL` are **read-only**. `dev.py` does not enforce that at the Django layer — it will happily use a read-write DSN if you give it one. The enforcement has to happen at the Postgres role level, on the Neon prod branch itself. Follow this checklist before setting `PROD_DATABASE_URL` anywhere.

### 1. Create a read-only role on the Neon prod branch

Neon's console (**Project → prod branch → Roles**) can create a role for you, but it won't scope permissions — by default a new Neon role can still write. Use SQL instead, run against the **prod** branch via `psql` or the Neon SQL editor:

```sql
-- Run against the PROD branch, as an owner/admin role
CREATE ROLE monitor_readonly LOGIN PASSWORD '<generate-a-strong-password>';

GRANT CONNECT ON DATABASE neondb TO monitor_readonly;
GRANT USAGE ON SCHEMA public TO monitor_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO monitor_readonly;

-- So tables created *after* this grant are still read-only for the role
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO monitor_readonly;
```

Notes:
- Do **not** grant `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `CREATE`, or anything on `SCHEMA neon_auth` unless a specific read need shows up later — start minimal.
- If you used the Neon console's Roles UI to create the role, still run the `GRANT`/`ALTER DEFAULT PRIVILEGES` statements above by hand — the UI doesn't offer a "read-only" toggle.
- Name the role something that signals its purpose (`monitor_readonly`, `devtools_ro`, etc.) so it's obvious in Neon's role list and in any future audit.

### 2. Get the role's connection string

In the Neon console, switch the "connect" panel's role/user dropdown to `monitor_readonly` (still on the **prod** branch) and copy the connection string. It has the same host as prod's main DSN but a different `user`/`password`.

### 3. Set `PROD_DATABASE_URL` in `backendServer/.env`

```
PROD_DATABASE_URL=postgresql://monitor_readonly:<password>@<prod-branch-host>/neondb?sslmode=require
```

Leave `DATABASE_URL` in the same file pointed at your dev branch, per the "On Dual Connection Strings" guidance above — `PROD_DATABASE_URL` is a separate, additive variable, not a replacement.

### 4. Confirm the `prod_readonly` alias connects

```bash
cd backendServer
DJANGO_ENV=dev uv run python manage.py dbshell --database=prod_readonly
```

Or, without dropping into `psql`, from `manage.py shell`:

```python
from django.db import connections
connections["prod_readonly"].ensure_connection()
print("connected:", connections["prod_readonly"].is_usable())
```

A successful connection confirms the DSN and role are wired correctly on the Django side.

### 5. Verify the role actually cannot write

This is the step that matters most — don't skip it. In the same `dbshell --database=prod_readonly` session, try something harmless and destructive-shaped:

```sql
CREATE TABLE ro_smoke_test (id int);
-- expected: ERROR: permission denied for schema public

INSERT INTO events_event (id) VALUES (-1);
-- expected: ERROR: permission denied for table events_event
```

Both must fail with a `permission denied` error. If either succeeds, the role has write access — stop, `DROP` anything you created with a properly-privileged role, fix the grants in step 1, and re-verify before using this DSN anywhere.

### 6. Security caveat

Setting `PROD_DATABASE_URL` means production database credentials now live in a local `backendServer/.env` file on a developer machine. Treat that seriously:

- `.env` must stay gitignored — never commit it, never paste its contents into a PR, issue, or chat log.
- Always use the read-only role from step 1 for this variable, never the prod owner/admin DSN. The entire point is to cap blast radius to reads even if the file leaks.
- If the machine is lost, compromised, or the role's password is suspected to have leaked, revoke/rotate immediately from the Neon console or via `ALTER ROLE monitor_readonly PASSWORD '<new-password>';`, then update `.env` on any machine still using it.
- When a role is no longer needed (e.g. a laptop is decommissioned), `DROP ROLE monitor_readonly;` rather than leaving it dangling.
