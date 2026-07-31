# Handoff — end of the suite 35 push, start of suite 36 (2026-07-29 ~21:45 UTC)

Repo: `/Users/ErenYeager/Desktop/hw/thecommons`. Read `CLAUDE.md` → `AGENTS.md` /
`ARCHITECTURE.md` / `CODING_STYLE.md` first.

Supersedes `docs/handoff-suite-35-2026-07-29.md` for anything they disagree on. That doc was
written *before* the release shipped; several of its predictions turned out wrong (listed
below).

## TL;DR

**Suite 35 is done and in prod.** The scheduler outage is fixed and *proven*, not inferred.
Three PRs merged and deployed today. One regression was introduced late in the session
(mine) and is not yet fixed — see 36.5.

| | |
|---|---|
| `origin/main` | `25f96e9` |
| Prod VM | `main` @ `25f96e9`, all 6 units active |
| Live Events | **189** (was 183) |
| Open PRs | none |
| Uncommitted | `notion-sync/STATE.md` (suite 36 ledger row) on branch `fix/orphan-recovery-window-widen` |

## What shipped today

| PR | Merge | Contents |
|---|---|---|
| #34 | `321da75` | Suites 31–35 as one release, 14 commits |
| #35 | `d5b4202` | 35.14 Chatham town coverage |
| #36 | `25f96e9` | healthcheck staleness window for `broadcast-orphan-recovery` |

Migrations applied to prod: `ingestion.0014_sourcerun`, `ingestion.0015_alter_stagedevent_status`,
`broadcast.0010_broadcastimage`, `events.0016_seed_chatham_towns`.

Also done by hand on prod (all authorized, all verified):
- `GRANT SELECT ON ingestion_sourcerun TO monitor_readonly` — confirmed via
  `information_schema.role_table_grants`.
- `healthcheck.{service,timer}` installed to `/etc/systemd/system/`, enabled, firing hourly.
- Ran `publish_all_approved()` to backfill the Chatham events.

## 35.1 is proven — do not re-open this

The deploy *was* the experiment. It runs `systemctl restart celery celerybeat …` over SSH and
the session closes seconds later — the exact sequence that killed the workers on 07-21.

| | |
|---|---|
| Units entered active | 17:26:13–15 UTC |
| Deploy SSH session closed | 17:26:15 UTC |
| Still `active` at | 17:30:12 UTC |
| **NRestarts** | **0** on all four |

`NRestarts=0` is the load-bearing number: `Restart=always` could have masked a continuing
teardown by silently resurrecting the workers, so a zero restart count is what proves they
never died. `ExecStart` is `/home/ubuntu/thecommons/backendServer/.venv/bin/celery` on all four.

Note the deploy's own `systemctl is-active` step proves nothing — it runs *inside* the SSH
session and it passed on 07-21 too.

## Corrections to the earlier handoff

1. **No manual `manage.py migrate` was ever needed.** The deploy job already does a guarded
   migrate (`.github/workflows/ci.yml`): `migrate --check`, then a `pg_dump | gzip`
   pre-migrate backup, then `migrate --noinput`. Step 2 of the old handoff was redundant.
2. **`broadcast.0010_broadcastimage` also shipped** — suite 31's image-upload schema. Not
   predicted anywhere.
3. **The "~26 dropped Chatham events" figure was wrong. The real number was 6**
   (siler-city 4, bynum 2). Drop-log lines overcount because skipped rows stay `approved` and
   **re-log on every run** — the same rows reappear each time. That is also why the count
   appeared to grow 18 → 26 between runs.
4. **No backfill migration was needed for 35.14.** A skipped row keeps
   `published_event=None`, so the approved→published sweep (`ingestion/services.py:103`)
   leaves it alone and the next publish run retries it. Adding the `Town` rows was sufficient.
5. **The predicted healthcheck first-run FAIL on `scrape-sources-daily` did not happen.**
   It reported OK at 10.2h (window 25h). Beat has been alive since the linger fix.
6. **`chapel-hill` existed in prod but was in no migration** — `events/0004` seeded only
   carrboro and pittsboro. Every fresh DB has been silently missing a covered town.
   `events/0016` now seeds it.

## ⚠️ Regression I introduced — fix this first (36.5)

PR #36 added `"broadcast-orphan-recovery": 7` to `DEFAULT_STALENESS_HOURS`
(`backendServer/events/management/commands/healthcheck.py:42`). **7h is too tight**, and prod
now has an hourly failing systemd unit:

```
✗ beat:broadcast-orphan-recovery  STALE — last run 9.7h ago (> 7h window)
✗ beat:weekly-digest-sunday       STALE — last run 215.1h ago (> 192h window)
Summary: 2 failing, 0 warning
```

The second FAIL is expected and correct (see below). The first is mine. Widen to **13h**
(two intervals + 1h grace) — decision already taken with the user. See ticket 36.5.

## 🚨 The open mystery — 36.4, highest-value unknown

**Beat sends tasks but is not persisting `last_run_at`.** Established facts:

- Beat logged `Scheduler: Sending due task broadcast-orphan-recovery` at **18:00:00 UTC**,
  exactly on schedule (`0 */6 * * *`).
- At **21:41 UTC**, `PeriodicTask` still read `last_run_at=2026-07-29 12:00:01`,
  `total_run_count=9` — unchanged, 3.7h later.
- Same database (`ep-late-smoke-ahkx1tkt-pooler...`), `DJANGO_ENV=prod` confirmed in
  `/proc/<beat pid>/environ`. **Not** a dev/prod DB split.
- No errors or warnings in `journalctl -u celerybeat` since the 17:56 restart.
- celery `Scheduler.sync_every = 3 * 60`, and `_last_sync` starts as `None`, so the *first*
  `apply_async` should sync immediately.

**Why this matters more than it looks:** `broadcast-orphan-recovery` is the *only* task that
has run since beat restarted at 17:56 (ingest/scrape fire at 07:30/08:00). So this is not an
orphan-recovery quirk — **the current beat process has never successfully persisted a
`last_run_at` at all.** If that generalizes, every staleness check is unreliable — which is
the exact mechanism suite 35 relies on to detect a dead scheduler.

**Leading hypothesis** — `django_celery_beat/schedulers.py`:

```python
446  def sync(self):
...
457              self._schedule[name].save()
458              _tried.add(name)
459          except (KeyError, TypeError, ObjectDoesNotExist):
460              _failed.add(name)
...
470          self._dirty |= _failed        # retry forever, silently
```

and `ModelEntry.save()` at line 171:

```python
174      obj = type(self.model)._default_manager.get(pk=self.model.pk)
```

A stale in-memory `pk` raises `ObjectDoesNotExist`, which is swallowed at 459 and retried
forever with **no log above DEBUG**. Beat runs `-l info`, so this would be invisible.

Against that hypothesis: `total_run_count=9` means the row was *not* recreated (a migration
re-seed would reset it to 0), and beat reloaded its schedule fresh at 17:56 *after* the last
migration ran. So the pk should be current. **Unresolved.**

**Cheapest decisive test, in order:**
1. Query `last_run_at` for `broadcast-orphan-recovery` after **00:00 UTC** (next fire). If it
   is still 12:00, persistence is broken for this process, not lagging.
2. Check `ingest-events-daily` after **08:00 America/New_York**. If that also fails to
   update, the bug is general and 36.4 becomes urgent.
3. Only then consider `systemctl restart celerybeat` — if `last_run_at` jumps forward on
   shutdown, it is a sync-timing bug; `Service.sync()` on close is a different path from
   `_do_sync()`. **This is a prod service restart — ask first.**

Run beat at `-l debug` temporarily to see the `Writing entries...` line at
`schedulers.py:448` if you need direct confirmation.

## Correct, expected FAIL — leave it alone

`weekly-digest-sunday` last ran **2026-07-20**. Beat was dead through Sunday 2026-07-26, so
**that week's digest was never sent to subscribers.** Decision taken with the user: let
Sunday **2026-08-02** send normally rather than back-send a stale digest. The healthcheck
stays FAIL until then. **This is honest signal, not a bug — do not "fix" it.**

## Prod data state

```
Events 189 — carrboro 95, pittsboro 69, None 15, chapel-hill 4, siler-city 4, bynum 2
StagedEvent — approved 27, duplicate 10, published 6
RawEvent 172, 0 unprocessed
```

- The **27 `approved`** rows are **Apex 15 + Durham 12** — correctly out of coverage, but they
  churn and re-log on every run forever. That is ticket 36.1.
- **15 events have `town = NULL`** (e.g. "Chatham YMCA Leprechaun Dash 5K/10K"). Ticket 36.2.

## Suite 36 — filed

`36.1`–`36.3` are already written into `notion-sync/OUTBOX.md` as a pending `NEW SUITE` block
(column `Open`). `36.4` and `36.5` are drafted but **not yet appended** — the session ended
before the user approved them.

| Ticket | Title |
|---|---|
| 36.1 | Terminal state for out-of-coverage towns so staged rows stop churning |
| 36.2 | Backfill the 15 live events with `town = NULL` |
| 36.3 | Alert on a *missed* weekly digest, not just a stale one |
| 36.4 | Beat is not persisting `last_run_at` |
| 36.5 | Widen `broadcast-orphan-recovery` window 7h → 13h |

## Still not done from the old handoff

- **Re-verify 35.13's dedupe on suite-34 code.** Now finally possible — 34 is deployed. The
  earlier check ran on pre-34 code so it did *not* validate 34.1's dedupe change.
- **35.10 local `.env` repoint** — UI shipped, `.env` change deferred.
- Load `/devtools/monitor?db=prod_readonly` and confirm the Runs tab shows real rows now that
  the GRANT is in place. Not visually confirmed this session.

## Environment gotchas that cost time

- **`notion-sync/OUTBOX.md` is gitignored**; `STATE.md` is tracked. **Every suite back to 17
  is `_(pending)_` — the Notion desktop app has never synced.** So today's tickets exist only
  in that local file, not on the board. There is no `NEW TICKET` change type; new tickets go
  in by editing the pending `NEW SUITE` block in place.
- **Use an absolute path to `oraclevps.key`.** The Bash tool's cwd persists between calls.
- **SSH to the prod VM needs explicit user approval naming the host** (`ubuntu@129.80.229.41`);
  the permission classifier blocks it otherwise. So does merging an agent-authored PR.
- `Event` is keyed by `uuid`, not `id` — `Count("id")` raises `FieldError`. Use `Count("uuid")`
  or `Count("pk")`.
- **`gh` hit transient `api.github.com` connection errors** mid-poll during one deploy watch.
  An `until` loop reading `--json status` treats a failed call as "not completed" and keeps
  waiting, which is the safe direction — but don't mistake those errors for a failed deploy.
- Backend tests: `cd backendServer && DJANGO_SETTINGS_MODULE=backend.settings.test uv run
  python manage.py test --noinput`. Run serially; parallel runs share one Neon test DB and
  produce bogus failures.
- **ruff E501 (100 cols) gates the whole CI**, including `deploy`. It bit this repo twice now.
  Run `uv run ruff check` before pushing.
