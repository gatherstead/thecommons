# Handoff — Suite 35 (prod scheduler outage) as of 2026-07-29 ~17:10 UTC

Repo: `/Users/ErenYeager/Desktop/hw/thecommons`. Read `CLAUDE.md` → `AGENTS.md` /
`ARCHITECTURE.md` / `CODING_STYLE.md` first.

## TL;DR

The prod scheduler outage is **fixed and verified on prod**. The repo work for suite 35 is
**committed, pushed, and CI-green** on PR #34. Nothing is deployed to prod yet beyond the
systemd unit files, which were applied by hand.

**The one thing to know:** "the commit failed to prod" was a CI lint gate, not a deploy
failure — a single 110-char line in suite 31. Fixed in `3998f5e`. **CI is now green.**
PR #34 has never been merged, so `deploy (oracle vm)` has never run.

## Current state

| | |
|---|---|
| Branch | `feat/suite-33-monitor-diagnostics-correctness` (pushed) |
| PR | **#34** → `main`, OPEN, **CI green**, MERGEABLE |
| `origin/main` | `034c787` |
| Prod VM repo | `main` @ `034c787` — **unchanged, nothing deployed** |
| Prod migrations | `ingestion.0013` (0014 + 0015 still unshipped) |
| Prod services | all 6 active, verified surviving SSH logout |

VM: `ubuntu@129.80.229.41`, key at repo root (`ssh.sh`). **Use an absolute path to
`oraclevps.key`** — the Bash tool's cwd persists between calls and relative paths break.

## What was actually wrong (settled — do not re-litigate)

All four Celery units ran `ExecStart=/snap/bin/uv …`. Snap execs its child in a transient
scope under `user@1001.service` — the *user* manager, not the unit's own cgroup. With
`Linger=no`, logind tore down the user slice when the deploy's SSH session ended. Celery
warm-shut-down and exited **0/SUCCESS**, which `Restart=on-failure` correctly declines to
restart.

Exact control group: `gunicorn` (`.venv/bin/gunicorn`, never through snap) entered active at
**2026-07-21 12:46:00** — the same deploy, the same logout that killed celery at **12:46:26** —
and was still up 8 days later. Same session, same teardown, opposite outcome.

Ruled out, don't chase: OOM (5903MB total, 1112MB used), Neon errors (exit was clean),
`CELERY_BEAT_MAX_LOOP_INTERVAL`, and Cloudflare/WAF on the Carrboro feed (see below).

## Already applied to prod by hand (NOT via CI/CD)

- All four units → `ExecStart=/home/ubuntu/thecommons/backendServer/.venv/bin/celery`,
  `Restart=always`. Verified alive from a fresh session after logout.
- `broadcast-worker` was running the **retired** `manage.py run_broadcast_worker` poll loop,
  which drains once and exits 0 — so the `broadcast` queue had **no consumer at all**. Now on
  the Celery queue; `inspect active_queues` lists `celery`, `scrape`, `broadcast`.
- Unique worker nodenames: `-n commons-{default,scrape,broadcast}@%%h`. **The doubled `%%`
  is required** — systemd expands a bare `%h` to the *user home directory*, not the hostname.
- `loginctl enable-linger ubuntu` (set by an earlier session; kept as defense-in-depth).
- Unit backups: `/root/unit-backups-20260729-163005/`.

⚠️ These unit files are also committed to the repo, so a future CI deploy is consistent with
the box. But **the VM's git checkout is still `main`@`034c787`** — it has none of the suite
31–35 application code.

## Corrections to earlier briefs (several were wrong)

1. **"VM fix applied 2026-07-29, backups at `/root/unit-backups-20260729/`" was FALSE.**
   That directory did not exist and all four units still ran snap-`uv`. Verified directly.
2. **"`scrape-sources-daily` has fired zero times ever" is now stale.** It ran at 07:30 on
   2026-07-29, and `ingest-events-daily` at 08:00 — an earlier session's `enable-linger` had
   already revived beat.
3. **"gunicorn had been up 68 days" is wrong.** Its real `ActiveEnterTimestamp` is
   2026-07-21 12:46:00 (8 days). The corrected version is stronger evidence, not weaker.
4. **Carrboro's frozen `last_polled` was SHARDING, not a WAF.** `INGEST_SHARD_COUNT=3`;
   day-of-year 210, `210 % 3 = 0`, Carrboro is id=1 → `1 % 3 = 1` → not eligible that day.
   Polled manually from the prod IP: HTTP 200, 56KB, 64 VEVENTs, 10 new events, no error.
   **The Cloudflare hypothesis is dead.** Note the monitor's probe structurally *cannot* find
   this class of bug — it runs from the operator's laptop, which is why 35.6 now prints a
   client-IP caveat in the UI.
5. **35.9's cited file was wrong.** The swallowed exception is at `source_run.py:139-140`,
   not `ics_importer.py:139-140` — identical line numbers, different file, because suite 33
   moved the loop into the shared `poll_sources_with_run_tracking`. Fixing the shared helper
   means the traceback now covers http/scraper polling too, which the ticket didn't ask for.

## Ingestion: fully caught up (done this session)

A full **unsharded** poll was run on prod (`poll_all_ics_sources(shard=None)` +
`poll_all_scraper_sources(shard=None)`), then standardize → dedup → safety → autopublish.

- **`The Plant NC` (id=4) polled for the first time ever** — 28 events imported.
- Carrboro: polled, 10 new events, then 0 on re-poll (correctly idempotent).
- Final: RawEvent **172**, **0 unprocessed**, StagedEvent 43 (33 approved / 10 duplicate),
  live Events **147 → 183**.

`cleanup_old_events` removed 7 raw events during one run — that's the dedupe-corpus erosion
suite 34 (34.1/34.2) fixes, still happening because 34 isn't deployed.

## 🚨 Biggest open finding — 35.14, needs a PRODUCT decision

The pipeline **silently drops** staged events whose Gemini-classified town has no `Town` row.
`events.Town` has exactly **3**: `carrboro`, `chapel-hill`, `pittsboro`.

Two runs dropped ~18 and ~26 events respectively, including:

```
Dropping staged event 'Growers & Makers Market' — no Town matches slug 'siler-city'
Dropping staged event 'Chatham County Parks and Recreation Summer Camp - Week 5' — no Town matches slug 'siler-city'
Dropping staged event 'Bynum Front Porch Music' — no Town matches slug 'bynum'
```

**Siler City and Bynum are both in Chatham County, and Pittsboro (already covered) is the
Chatham County seat.** An event titled "Chatham County Parks and Recreation Summer Camp" is
being discarded. Apex/Durham are defensibly out of scope; `siler-city` and `bynum` are not.

Questions for the user, not for an engineer to guess:
- Should Siler City / Bynum be covered Towns? If so, add them and consider a backfill.
- Should an unmatched Town be a *drop*, or a held-for-review state so it's visible?
- Should the monitor surface a "dropped: unmatched town" bucket? Today these sources just
  look like `raw > 0, published = 0` with no explanation.

## Ticket status

| Ticket | Status |
|---|---|
| 35.1 units off snap-uv (+ nodenames) | **In Prod**, logout-verified |
| 35.9 ICS re-test | **In Prod** — poll succeeded, WAF theory dead |
| 35.11 broadcast-worker drift | **In Prod** — queue has a consumer |
| 35.13 RawEvents 618/619/620 | **In Prod** — resolved, see caveat below |
| 35.2–35.7 | **Staged for Prod** — in PR #34, CI green |
| 35.8 migrate prod (35.12 merged in) | **In Progress** — blocked on merging #34 |
| 35.10 local `DATABASE_URL` | **In Progress** — UI shipped; `.env` repoint deferred |
| 35.14 unmatched-Town drops | **Open** — needs product decision |

**35.13 caveat:** 618/620 both resolved to `status="duplicate"` with `duplicate_of=None` (they
deduped against the already-published Event, not each other) and 619 published independently —
correct outcome, but this ran on **pre-suite-34** code, so it does **not** validate 34.1's
dedupe change. Re-check after #34 merges.

## Next steps, in order

1. **Merge PR #34.** CI is green. It carries **five** suites (31 broadcast — client-facing,
   32, 33, 34, 35), 11 commits ahead of main. Review it as a release, not a feature PR.
2. **Let CI/CD deploy**, then on the VM run `manage.py migrate` for `0014_sourcerun` +
   `0015_alter_stagedevent_status`.
3. ⚠️ **Have this ready:** `GRANT SELECT ON ingestion_sourcerun TO monitor_readonly;` —
   `ALTER DEFAULT PRIVILEGES` only covers tables created by the role that ran it. Suite 33's
   `resolve_source_runs_state()` distinguishes SQLSTATE `42P01` (missing table) from `42501`
   (missing GRANT), so the monitor will say which one you hit.
4. Load `/devtools/monitor?db=prod_readonly` and confirm the Runs tab shows real rows.
5. Install the healthcheck timer (`deploy/healthcheck.{service,timer}`). **It will FAIL on
   first run if `scrape-sources-daily` looks stale** — 35.2 promoted never-run/stale to `FAIL`.
   That's intended signal; documented in `DEPLOY.md`.
6. Re-verify 35.13's dedupe on suite-34 code.
7. Get a product answer on 35.14.

## Gotchas that cost time this session

- **Parallel subagents share one Neon test DB.** Concurrent `manage.py test` runs produce
  bogus `UndefinedTable` / `PeriodicTask.DoesNotExist` failures on tests nobody touched.
  Always re-run the full suite **serially** before trusting a green.
- **Use `--noinput`.** An aborted run leaves the test DB behind and the next run blocks on an
  interactive "delete it?" prompt that dies with `EOFError`.
- **`| tail` masks exit status.** Use `set -o pipefail` and echo `${PIPESTATUS[0]}` — a hard
  failure otherwise reads as exit 0.
- **`notion-sync/OUTBOX.md` is gitignored**; `STATE.md` is tracked. Suite 35 lives in the
  outbox as a still-unapplied `NEW SUITE` block (every suite back to 17 is `_(pending)_` —
  the desktop app has never synced). There is **no `NEW TICKET` change type**, so new tickets
  must be added by editing the pending block in place.
- Backend tests: `cd backendServer && DJANGO_SETTINGS_MODULE=backend.settings.test uv run
  python manage.py test --noinput` (513 tests, OK).
