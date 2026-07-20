"""Read-through cache for broadcast access resolution.

resolve_access() runs on every authed broadcast API request via
_BroadcastTierPermission, so a naive implementation fires a Neon read per
request (worst case: a client polling a running job every few seconds). This
module caches the two identity lookups resolve_access() makes — the JWT
path's BroadcastAccess grant, and the trial-code path's matched AccessCode —
so repeat resolutions within ACCESS_TTL don't hit the DB.

Consumption counts (AccessCodeUse.count(), max_uses enforcement) are
deliberately NOT cached here — resolve_access() always re-checks those live
so caching never weakens the max_uses guard.

27.5 added the job-status helpers below: job_detail() polls (broadcastWeb hits
GET /broadcast/jobs/{id} every 3s while a job runs) are served straight from
Redis instead of re-querying BroadcastSubmission + its targets on every poll.
Every status transition in services.py/worker.py/runner.py writes the fresh
payload through to this cache, so job_detail() only touches Neon on a cold
cache (first read after a restart/eviction).
"""

from django.core.cache import cache

ACCESS_TTL = 300  # seconds
JOB_TTL = 60 * 60  # seconds — comfortably longer than any job's lifetime, so
# terminal-state polls (done/failed/canceled) keep hitting cache, not Neon.


def _jwt_key(email: str) -> str:
    return f"broadcast:access:jwt:{email}"


def get_jwt_access(email: str) -> dict | None:
    return cache.get(_jwt_key(email))


def set_jwt_access(email: str, data: dict) -> None:
    cache.set(_jwt_key(email), data, ACCESS_TTL)


def invalidate_jwt_access(email: str) -> None:
    cache.delete(_jwt_key(email))


def _code_key(code_hash: str) -> str:
    return f"broadcast:access:code:{code_hash}"


def get_code_meta(code_hash: str) -> dict | None:
    return cache.get(_code_key(code_hash))


def set_code_meta(code_hash: str, data: dict) -> None:
    cache.set(_code_key(code_hash), data, ACCESS_TTL)


def invalidate_code_meta(code_hash: str) -> None:
    cache.delete(_code_key(code_hash))


def _job_key(job_id) -> str:
    return f"broadcast:job:{job_id}"


def get_job_payload(job_id) -> dict | None:
    return cache.get(_job_key(job_id))


def set_job_payload(job_id, payload: dict) -> None:
    cache.set(_job_key(job_id), payload, JOB_TTL)


def invalidate_job(job_id) -> None:
    cache.delete(_job_key(job_id))
