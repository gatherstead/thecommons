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
