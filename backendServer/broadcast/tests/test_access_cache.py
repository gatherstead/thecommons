"""DB-tier tests for the broadcast.cache read-through layer around resolve_access.

Uses @tag("db") + TestCase (real Postgres test DB). Test settings swap CACHES to
LocMemCache, so no Redis is needed here. JWT path stubs verify_better_auth_jwt via
unittest.mock.patch — no JWKS hit.
"""

from unittest import mock

from django.core.cache import cache as django_cache
from django.test import RequestFactory, TestCase, tag

from broadcast.access import hash_code, redeem_upgrade_code, resolve_access
from broadcast.models import AccessCode, AccessCodeUse, BroadcastAccess


def _make_request(*, auth_header: str | None = None, code_header: str | None = None):
    factory = RequestFactory()
    headers = {}
    if auth_header:
        headers["HTTP_AUTHORIZATION"] = auth_header
    if code_header:
        headers["HTTP_X_BROADCAST_ACCESS_CODE"] = code_header
    req = factory.post("/", **headers)  # type: ignore[arg-type]
    req.data = {}  # type: ignore[attr-defined]
    return req


def _make_code(
    label="testclient",
    tier=2,
    max_uses=3,
    is_active=True,
    raw="RAWCODE",
    kind=AccessCode.KIND_TRIAL,
):
    return AccessCode.objects.create(
        code_hash=hash_code(raw),
        label=label,
        kind=kind,
        tier=tier,
        max_uses=max_uses,
        is_active=is_active,
    )


def _patch_jwt(claims):
    return mock.patch("broadcast.access.verify_better_auth_jwt", return_value=claims)


@tag("db")
class JWTPathCacheTest(TestCase):
    def setUp(self):
        django_cache.clear()

    def test_second_resolution_within_ttl_skips_db_lookup(self):
        BroadcastAccess.objects.create(email="alice@example.com", tier=2)
        req1 = _make_request(auth_header="Bearer faketoken")
        req2 = _make_request(auth_header="Bearer faketoken")

        with _patch_jwt({"email": "alice@example.com"}):
            first = resolve_access(req1)
            # Only the first resolution should touch broadcast_broadcastaccess —
            # the second must be served entirely from cache.
            with self.assertNumQueries(0):
                second = resolve_access(req2)

        self.assertEqual(first.tier, 2)
        self.assertEqual(second.tier, 2)
        self.assertEqual(second.identity, "alice@example.com")

    def test_no_grant_row_is_also_cached(self):
        req1 = _make_request(auth_header="Bearer faketoken")
        req2 = _make_request(auth_header="Bearer faketoken")

        with _patch_jwt({"email": "nobody@example.com"}):
            first = resolve_access(req1)
            # The permanent-grant lookup is cached (0 queries), but a tier-0
            # account always gets a live bound-trial-code check (1 query) —
            # same "never cache consumption/liveness" policy as the anonymous
            # code path, so an expired/revoked bound trial can't serve stale
            # access from cache.
            with self.assertNumQueries(1):
                second = resolve_access(req2)

        self.assertEqual(first.tier, 0)
        self.assertEqual(second.tier, 0)

    def test_redeeming_upgrade_code_invalidates_cache(self):
        BroadcastAccess.objects.create(email="alice@example.com", tier=0)
        req = _make_request(auth_header="Bearer faketoken")

        with _patch_jwt({"email": "alice@example.com"}):
            stale = resolve_access(req)
        self.assertEqual(stale.tier, 0)

        upgrade_code = AccessCode.objects.create(
            code_hash=hash_code("UPGRADERAW"),
            label="acme",
            kind=AccessCode.KIND_UPGRADE,
            tier=2,
            max_uses=None,
        )
        redeem_upgrade_code("alice@example.com", "UPGRADERAW")

        req2 = _make_request(auth_header="Bearer faketoken")
        with _patch_jwt({"email": "alice@example.com"}):
            fresh = resolve_access(req2)
        self.assertEqual(fresh.tier, 2)
        self.assertEqual(upgrade_code.tier, 2)

    def test_post_save_on_broadcast_access_invalidates_cache(self):
        grant = BroadcastAccess.objects.create(email="bob@example.com", tier=1)
        req = _make_request(auth_header="Bearer faketoken")
        with _patch_jwt({"email": "bob@example.com"}):
            stale = resolve_access(req)
        self.assertEqual(stale.tier, 1)

        grant.tier = 2
        grant.save()

        req2 = _make_request(auth_header="Bearer faketoken")
        with _patch_jwt({"email": "bob@example.com"}):
            fresh = resolve_access(req2)
        self.assertEqual(fresh.tier, 2)


@tag("db")
class CodePathCacheTest(TestCase):
    def setUp(self):
        django_cache.clear()

    def test_second_resolution_within_ttl_skips_code_scan(self):
        _make_code(raw="MYCODE", max_uses=5)
        req1 = _make_request(code_header="MYCODE")
        req2 = _make_request(code_header="MYCODE")

        first = resolve_access(req1)
        self.assertEqual(first.tier, 2)
        self.assertEqual(first.uses_remaining, 5)

        with self.assertNumQueries(2):
            # 1 query to fetch the AccessCode row by cached id, 1 to count uses —
            # no scan over AccessCode.objects.filter(is_active=True, kind=TRIAL).
            second = resolve_access(req2)
        self.assertEqual(second.tier, 2)
        self.assertEqual(second.uses_remaining, 5)

    def test_near_exhausted_code_still_denied_on_cache_hit(self):
        """Caching the code's identity must never weaken max_uses enforcement:
        uses().count() and the over-use guard must still run live on a cache hit."""
        code = _make_code(raw="EXCODE", max_uses=2)
        req_warm = _make_request(code_header="EXCODE")
        warm = resolve_access(req_warm, draft_id="draft-1")
        self.assertEqual(warm.tier, 2)

        # Consume both slots after the identity is already cached.
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-1")
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-2")

        req_new = _make_request(code_header="EXCODE")
        denied = resolve_access(req_new, draft_id="draft-3")
        self.assertEqual(denied.tier, 0)
        self.assertIsNone(denied.code)

        # An already-counted draft is still allowed through, exactly as the
        # uncached path behaves.
        req_counted = _make_request(code_header="EXCODE")
        allowed = resolve_access(req_counted, draft_id="draft-1")
        self.assertEqual(allowed.tier, 2)
        self.assertEqual(allowed.uses_remaining, 0)

    def test_code_deactivation_invalidates_cache(self):
        code = _make_code(raw="DEACTCODE", max_uses=None)
        req1 = _make_request(code_header="DEACTCODE")
        warm = resolve_access(req1)
        self.assertEqual(warm.tier, 2)

        code.is_active = False
        code.save()

        req2 = _make_request(code_header="DEACTCODE")
        result = resolve_access(req2)
        self.assertEqual(result.tier, 0)
