# Incident: prod scheduler dead 8 days (2026-07-21 → 2026-07-29)

Forensics done 2026-07-29 against the live VM (`ubuntu@129.80.229.41`) and an
approved `prod_readonly` read. This file is the record of what was *observed*,
what was *changed*, and what is still *outstanding*. Suite 34 (shipped) and
suite 35 (open) both trace back to it.

## Symptom

The `/devtools/monitor` ingestion dashboard showed "Direct Host Submission" with
9 raw events: 3 unprocessed, 2 duplicate, 4 published. The 3 unprocessed rows
(`RawEvent` 618/619/620) had `processed=False` and no `StagedEvent`.

## Root cause

Not a Gemini failure. **Celery beat and the worker had been dead for 8 days.**

Every `PeriodicTask.last_run_at` was frozen at the same instant:

| Task | Last run | Runs ever |
|---|---|---|
| `broadcast-orphan-recovery` | 2026-07-21 12:46:13 | 6 |
| `celery.backend_cleanup` | 2026-07-21 12:46:13 | 12 |
| `weekly-digest-sunday` | 2026-07-20 22:35 | 4 |
| `ingest-events-daily` | 2026-06-21 | 2 |
| `scrape-sources-daily` | never | 0 |

`RawEvent` 618 was submitted at **12:51:37 — five minutes after beat's last
heartbeat**. 619 and 620 followed on 07-25 and 07-26, into a queue with no
consumer. That is the entire explanation for the 3 stuck rows.

### Mechanism

`systemctl status celery` showed the tell:

```
Active: inactive (dead) since Tue 2026-07-21 12:46:26 UTC
Duration: 32.421s
Main PID: 721260 (code=exited, status=0/SUCCESS)
```

A **clean exit**, not a crash. The system journal for that window shows the
user session terminating immediately beforehand:

```
12:46:23  worker: Warm shutdown (MainProcess)
12:46:26  systemd[720919]: Reached target shutdown.target - Shutdown
12:46:26  systemd[1]: user@1001.service: Deactivated successfully
12:46:26  systemd[1]: Removed slice user-1001.slice - User Slice of UID 1001
12:46:26  systemd[1]: celery.service: Deactivated successfully
```

All four Celery-family units run `ExecStart=/snap/bin/uv`, and snap executes its
child inside a transient scope under `user@1001.service` — the *user* manager,
not the service cgroup. With `Linger=no`, logind tears down `user-1001.slice`
when the last `ubuntu` login session ends, taking every snap scope with it. The
worker exits `0/SUCCESS`, and `Restart=on-failure` correctly declines to restart
a clean exit.

**The control group is decisive:**

| Unit | ExecStart | Outcome |
|---|---|---|
| `celery`, `celerybeat`, `scrape-worker`, `broadcast-worker` | `/snap/bin/uv` | all dead |
| `gunicorn` | `.venv/bin/gunicorn` | up 68 days |
| `nextjs` | `/usr/bin/npm` | up 68 days |

100% correlation with snap, 0% with anything else. The VM never rebooted
(`uptime` = 68 days) and memory was never a factor.

This also explains the two long-standing anomalies: `ingest-events-daily` at 2
lifetime runs and `scrape-sources-daily` at 0 are not separate bugs. Beat rarely
survived long enough to reach a 3:30/4:00am cron, because it died at the end of
whichever deploy last started it.

Because the site itself (`gunicorn`) stayed up, nothing looked wrong.

## Changes applied to prod (2026-07-29)

Only one, and it is what is currently holding the stack up:

```bash
sudo loginctl enable-linger ubuntu     # Linger=yes
sudo systemctl restart celery celerybeat scrape-worker broadcast-worker
```

Verified `celery`, `celerybeat`, and `scrape-worker` survive an SSH
login→logout cycle — the only test that actually exercises the failure mode.

**The units themselves are unchanged on the VM**: still `/snap/bin/uv`, still
`Restart=on-failure`. Prod is one `loginctl disable-linger` away from the same
outage.

> ⚠️ Ticket 35.1 carries a note claiming a VM-side unit fix was applied on
> 2026-07-29 with backups at `/root/unit-backups-20260729/`. **That is false.**
> The directory does not exist and the units are untouched. Do not skip 35.1's
> real work on the strength of that note.

## Still outstanding

1. **`broadcast-worker` is dead and its installed unit is stale.** The VM copy
   runs `manage.py run_broadcast_worker` — documented in
   `backendServer/AGENTS.md` as a *debug helper, not a service entrypoint*, and
   superseded by suite 25. The repo copy at `deploy/broadcast-worker.service:24`
   is already correct (`celery -A backend worker -Q broadcast -c 1 -l info`);
   prod simply drifted. Fix is a `cp` + `daemon-reload` + `restart`. This was
   authorized but not executed. See 35.11.
2. **The `broadcast` queue has no consumer.** 9 pending messages, all
   `broadcast.tasks.recover_broadcast_orphans` no-ops. No user submissions are
   stranded (prod: 15 `done`, 1 `canceled`, latest 2026-06-15), but beat now
   adds one every 6h and the backlog grows until (1) is fixed.
3. **The 3 stuck RawEvents have not drained yet.** The `celery` queue is empty —
   the original messages are gone from Redis, not merely delayed, so they can
   only recover via `standardize_all_unprocessed` in the nightly pipeline.
   `ingest-events-daily` fires at 4:00am America/New_York. Confirm 618/619/620
   reach `processed=True`. Note 618 and 620 are the *same* event and should
   collapse to a duplicate under suite 34's dedupe fix.
4. **Prod runs pre-suite-34 code.** Prod is at migration `0013`;
   `0014_sourcerun` and `0015_alter_stagedevent_status` are both unshipped, so
   the monitor's run-history tab is blind against `prod_readonly`.

## Verification commands

```bash
ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41

systemctl is-active celery celerybeat scrape-worker broadcast-worker gunicorn
loginctl show-user ubuntu --property=Linger          # must be yes

# the real test — must be a NEW session after a logout
ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 'systemctl is-active celery celerybeat'

# every queue needs a consumer; a queue with depth and no consumer is silent
cd /home/ubuntu/thecommons/backendServer
uv run celery -A backend inspect active_queues | grep -o "'name': '[a-z]*'"
uv run python manage.py healthcheck
```
