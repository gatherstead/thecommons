# 16.1 — Neon Dev Branch Setup (Runbook)

Transient doc — delete once you've followed it and confirmed the dev branch works.
Spec: [`docs/dev-db-isolation.md`](dev-db-isolation.md).

## Prereqs / facts verified
- Settings select on `DJANGO_ENV` (`backend/settings/__init__.py`); local has no `DJANGO_ENV`, so it defaults to `dev`. The VM sets `DJANGO_ENV=prod`.
- Guard 1 (present): `settings/dev.py` raises `RuntimeError` at startup if `DATABASE_URL` is unset.
- Guard 2 (present): `seed_dev` raises `CommandError` when `DEBUG` is off, unless `--force`.
- Frontend `src/lib/db.ts` reads `process.env.DATABASE_URL` and throws if missing.
- `theCommonsWeb/.env` is a stale Vite-era file (`VITE_*`); the live file is `theCommonsWeb/.env.local`, which already contains a `DATABASE_URL` — you are **replacing** that value, not adding a new key.

## Steps

1. **Create the dev branch (Neon console — manual)**
   - console.neon.tech → your project → **Branches** → **Create branch**.
   - Parent: `main` (prod). Name: `dev` (or `arya-dev`).
   - Open the new branch → copy its **connection string**. Same shape as prod, different branch host. Keep `?sslmode=require`.

2. **Point the backend at the dev branch**
   - Edit `backendServer/.env`, replace the `DATABASE_URL` value with the dev-branch string.
   - Leave the prod VM's `.env` untouched.

3. **Point the frontend at the dev branch**
   - Edit `theCommonsWeb/.env.local` (NOT `.env`), replace the existing `DATABASE_URL` value with the same dev-branch string.

4. **Migrate the dev branch**
   ```bash
   cd backendServer
   uv run python manage.py migrate
   ```
   The branch snapshot already has the `public` schema from prod; this just applies anything newer. The `neon_auth` schema rides along in the snapshot — no extra auth wiring.

5. **Seed the dev branch**
   ```bash
   uv run python manage.py seed_dev
   ```
   Idempotent (`get_or_create`). Re-running prints non-zero "already existed" counts and creates nothing new.

6. **Verify isolation with a real signup**
   - `cd theCommonsWeb && pnpm dev`, open `localhost:3000/auth`, sign up.
   - Confirm the row landed on the **dev branch**, not prod:
     ```bash
     # dev branch (local .env)
     psql "<dev-branch-url>" -c 'select email, created_at from neon_auth.users order by created_at desc limit 3;'
     # prod (should NOT show the new signup)
     psql "<prod-url>" -c 'select email, created_at from neon_auth.users order by created_at desc limit 3;'
     ```

## Acceptance check
- [ ] `backendServer/.env` + `theCommonsWeb/.env.local` both point at the dev branch.
- [ ] `seed_dev` populated the branch; a second run is a no-op.
- [ ] A `localhost:3000` signup appears on the dev branch and is absent from prod.

## Code/doc changes from this ticket
- None. Both guards described in the spec already exist and fire (verified `dev.py` l17–22, `seed_dev.py` l151–155). `docs/dev-db-isolation.md` matches the code — no drift found.
