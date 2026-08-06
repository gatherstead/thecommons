# Handoff — broadcast extension autofill (2026-08-06)

Context for a fresh Claude Code session. Two of three reported bugs are fixed and
live in prod; one is open with a strong, evidence-backed hypothesis and an
untested fix.

## Shipped this session

`f4cb243` on `main`, deployed to prod (CI run `31130194142`, all jobs green).
It carried suite 50 as well — its two one-way category-drop migrations
(`events/0026`, `ingestion/0023`) applied to prod. Pre-migrate backup at
`/home/ubuntu/backups/pre-migrate-20260806-230147.sql.gz` on the VM.

| Reported issue | Status |
|---|---|
| Free-trial access code denied | **Fixed, confirmed by user** |
| AI autofill wiping the form / bad phone numbers | **Fixed, confirmed by user** |
| Extension doesn't open a tab, says "not available" | **OPEN** — see below |

### Issue 1 (closed)

Root cause: the admin sales dashboard mints the *next* trial code as soon as the
current one is copied, but `expires_at` was stamped at mint time. A slot nobody
had copied in 3 days handed out an already-dead code while the panel advertised
"valid 3 days from when it's copied". Fixed via `start_trial_clock()` (clock
starts at hand-off) plus `ensure_sales_slots()` rotating an already-expired
trial code. Codes are also whitespace-stripped now, both ends.

**Do not chase the 403 on `POST /broadcast/redeem`.** It is by design and will
appear on every trial-code verification. `handleVerifyCode` in `App.tsx` tries
the code as an UPGRADE code first, and a TRIAL code legitimately 403s there
before the `getAccess()` trial fallback succeeds. The user flagged this as "it
gave 403 but actually redeemed" — working as intended, just noisy. Worth
cleaning up someday (403 is doing double duty as "wrong code kind" and "denied";
see the `broadcast-403-overload` memory) but it is not a bug.

## Issue 3 (OPEN) — no tab opens on autofill

### Symptom

User clicks a destination in Speed Submit. No tab opens. UI shows "not
available". Network tab looks healthy. Persists after deleting the duplicate
extension.

### What's already been ruled out

- **Duplicate extension** — user had two installs: `magppdjbmgkbablgiechmcoiklhpbian`
  (unpacked dev) and `jidmhdmlbjfnblbheglmodhpcjhafjmi` (Web Store). They deleted
  the unpacked one and kept the Web Store one. **The symptom persisted**, and
  deleting the dev copy plausibly made it *deterministic* — see below.
- **The SPA's extension ID config** — the prod bundle references only
  `jidmhdmlbjfnblbheglmodhpcjhafjmi`. Verified against the live bundle.
- **`direct-recipe` 403s** — these were real (shared Cloudflare-edge rate-limit
  bucket) and are fixed; rate limiting is now per-client, verified end to end.
  A `direct-recipe` failure no longer masquerades as "not available".

### Prime hypothesis: the published Web Store build is stale

The manifest version was last bumped to `0.3.0` on **2026-07-26** (`1d4d43d`).
Since that bump, the extension changed substantially with **no version bump**:

```
git diff --stat 1d4d43d..HEAD -- broadcastExtension/
 broadcastExtension/background.js | 110 ++++++--
 broadcastExtension/content.js    | 435 +++++++++++++++++++-----
```

Critically, `chrome.runtime.onConnectExternal` — the listener that receives the
SPA's fill request — was introduced on **2026-08-04** in `087f5e6` (suites
48+49), i.e. *after* the 0.3.0 bump. So a Web Store build published as "0.3.0"
can predate it while being indistinguishable in `chrome://extensions`.

The failure chain that produces exactly this symptom:

1. `sendFillWithAck()` (`broadcastWeb/src/hooks/useExtension.ts`) calls
   `runtime.connect(extensionId, { name: "fill" })`.
2. Old build has no `onConnectExternal` listener → the port immediately
   disconnects.
3. `port.onDisconnect` fires → resolves `{ kind: "dispatch-failed" }`.
4. `fillOne()` in `App.tsx` maps that to `"unavailable"` → **"not available"**,
   and `handleFill()` — the only thing that calls `chrome.tabs.create` — is
   never reached, so **no tab opens**.

This also explains why the extension still *detects* as installed: `ping` goes
through `onMessageExternal`, which has existed since long before 0.3.0. Detection
works, dispatch doesn't.

### How to confirm (do this first — 2 minutes, no code changes)

In `chrome://extensions`, open the Web Store build's **service worker** DevTools
and check whether the running code contains the listener:

```js
chrome.runtime.onConnectExternal.hasListeners()   // false  => stale build, hypothesis confirmed
```

Or view its `background.js` in Sources and grep for `onConnectExternal` /
`fillAckPorts`. Absent = confirmed.

Cross-check: load `broadcastExtension/` unpacked from the current repo, add its
ID to `VITE_BROADCAST_EXTENSION_ID` locally, and try a fill against a local SPA.
If the tab opens with the unpacked build but not the store build, that settles it.

### The fix (untested)

1. Bump `broadcastExtension/manifest.json` `version` to `0.4.0`.
2. Repackage (`extensionzipper.sh` at repo root) and publish to the Web Store.
   Review latency is on Google, not you — the user may need the unpacked build
   in the meantime.
3. Consider a CI guard: fail if `broadcastExtension/**` changed since the last
   commit that touched `manifest.json`'s `version`. This drift is what made a
   two-week-old bug invisible.

### If the hypothesis is wrong

Next candidates, in order:

- **Origin rejection.** `ALLOWED_ORIGINS` in `background.js` and
  `externally_connectable.matches` in the manifest both list exactly
  `https://broadcast.thecommons.town`, `http://localhost:5173`,
  `http://127.0.0.1:5173`. A mismatched origin makes `onConnectExternal`
  `port.disconnect()` immediately — identical symptom. Confirm which origin the
  user is actually on.
- **`recipe.url` missing.** `handleFill()` throws `"recipe has no url"` before
  `chrome.tabs.create`, producing `dispatch-error` → also "not available", also
  no tab. Check the `direct-recipe` response body for a `url` field.
- **Missing host permission** for the destination — but note this fails
  *after* the tab opens (silent no-fill), so it does not match "no tab opens".

## Gotchas worth knowing

- `broadcast/` is isolation-contracted: `routing.py` must not import from
  `events`, and never use the ORM inside `sync_playwright`.
- Backend tests: `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python
  manage.py test --noinput` (always `--noinput`; a stale test DB otherwise hangs
  on an interactive prompt). `--tag=fast` no-DB, `--tag=db` Postgres.
- The Neon test DB is shared across concurrent sessions/subagents — parallel runs
  collide and produce untrustworthy failures.
- Prod deploys are automatic on push to `main`, gated on tests. GitHub can take
  **10+ minutes** to even create the run; don't conclude it failed early. Manual
  fallback is in `DEPLOY.md`, and the build-arg subshell is mandatory or the
  frontends get placeholder `VITE_*` values baked in.

## Not done

- `docs/broadcast.md` not updated for any of this.
- Notion board / `notion-sync/OUTBOX.md` untouched — no suite recorded.
- This file is untracked; delete it or move it into `docs/` as you prefer.
