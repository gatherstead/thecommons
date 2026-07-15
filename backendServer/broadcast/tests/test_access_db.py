"""DB-tier tests for broadcast.access.resolve_access, GET /broadcast/access, and preview metering.

Uses @tag("db") + TestCase (real Postgres test DB).
JWT path stubs verify_better_auth_jwt via unittest.mock.patch — no JWKS hit.
"""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache as django_cache
from django.test import RequestFactory, TestCase, override_settings, tag
from django.utils import timezone
from rest_framework.test import APIClient

from broadcast.access import (
    AccessResult,
    bind_trial_code,
    hash_code,
    redeem_upgrade_code,
    resolve_access,
)
from broadcast.models import AccessCode, AccessCodeRedemption, AccessCodeUse, BroadcastAccess


def _make_request(
    *,
    auth_header: str | None = None,
    code_header: str | None = None,
    data: dict | None = None,
):
    factory = RequestFactory()
    headers = {}
    if auth_header:
        headers["HTTP_AUTHORIZATION"] = auth_header
    if code_header:
        headers["HTTP_X_BROADCAST_ACCESS_CODE"] = code_header
    req = factory.post("/", **headers)  # type: ignore[arg-type]
    req.data = data or {}  # type: ignore[attr-defined]
    return req


def _make_code(
    label="testclient",
    tier=2,
    max_uses=3,
    is_active=True,
    expires_at=None,
    raw="RAWCODE",
    kind=AccessCode.KIND_TRIAL,
):
    # NOTE: AccessCode.save() forces tier=2 for KIND_TRIAL regardless of `tier`.
    return AccessCode.objects.create(
        code_hash=hash_code(raw),
        label=label,
        kind=kind,
        tier=tier,
        max_uses=max_uses,
        is_active=is_active,
        expires_at=expires_at,
    )


@tag("db")
class JWTPathTest(TestCase):
    def _patch_jwt(self, claims):
        return mock.patch("broadcast.access.verify_better_auth_jwt", return_value=claims)

    def test_jwt_with_grant_row_returns_tier(self):
        BroadcastAccess.objects.create(email="alice@example.com", tier=2)
        req = _make_request(auth_header="Bearer faketoken")
        with self._patch_jwt({"email": "alice@example.com"}):
            result = resolve_access(req)
        self.assertEqual(result.tier, 2)
        self.assertEqual(result.identity, "alice@example.com")
        self.assertFalse(result.is_trial)
        self.assertIsNone(result.uses_remaining)
        self.assertIsNone(result.code)

    def test_jwt_no_grant_row_returns_tier_0_with_email_identity(self):
        req = _make_request(auth_header="Bearer faketoken")
        with self._patch_jwt({"email": "unknown@example.com"}):
            result = resolve_access(req)
        self.assertEqual(result.tier, 0)
        self.assertEqual(result.identity, "unknown@example.com")
        self.assertEqual(result.client_label, "unknown@example.com")
        self.assertFalse(result.is_trial)

    def test_jwt_without_email_claim_returns_tier_0(self):
        req = _make_request(auth_header="Bearer faketoken")
        with self._patch_jwt({"sub": "user123"}):
            result = resolve_access(req)
        self.assertEqual(result.tier, 0)
        self.assertIsNone(result.identity)

    def test_jwt_case_insensitive_email_lookup(self):
        BroadcastAccess.objects.create(email="bob@example.com", tier=1)
        req = _make_request(auth_header="Bearer faketoken")
        with self._patch_jwt({"email": "BOB@EXAMPLE.COM"}):
            result = resolve_access(req)
        self.assertEqual(result.tier, 1)
        self.assertEqual(result.identity, "bob@example.com")

    def test_invalid_jwt_returns_tier_0_without_trying_code(self):
        # Even if a code header is also present, invalid JWT stops resolution.
        _make_code(raw="VALIDCODE")
        req = _make_request(auth_header="Bearer badtoken", code_header="VALIDCODE")
        with self._patch_jwt(None):
            result = resolve_access(req)
        self.assertEqual(result.tier, 0)
        self.assertIsNone(result.identity)


@tag("db")
class CodePathTest(TestCase):
    def test_valid_code_in_budget_via_header(self):
        code = _make_code(raw="MYCODE", max_uses=5)
        req = _make_request(code_header="MYCODE")
        result = resolve_access(req)
        self.assertEqual(result.tier, 2)
        self.assertTrue(result.is_trial)
        self.assertEqual(result.uses_remaining, 5)
        self.assertEqual(result.identity, "testclient")
        self.assertEqual(result.client_label, "testclient")
        self.assertEqual(result.code, code)

    def test_valid_code_in_budget_via_request_data(self):
        _make_code(raw="DATACODE", tier=2, max_uses=3)
        req = _make_request(data={"access_code": "DATACODE"})
        result = resolve_access(req)
        self.assertEqual(result.tier, 2)
        self.assertTrue(result.is_trial)
        self.assertEqual(result.uses_remaining, 3)

    def test_uses_remaining_decrements_with_uses(self):
        code = _make_code(raw="COUNTCODE", max_uses=3)
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-1")
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-2")
        req = _make_request(code_header="COUNTCODE")
        result = resolve_access(req, draft_id="draft-3")
        self.assertEqual(result.uses_remaining, 1)

    def test_exhausted_code_with_counted_draft_id_allowed(self):
        code = _make_code(raw="EXCODE", max_uses=2)
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-A")
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-B")
        req = _make_request(code_header="EXCODE")
        result = resolve_access(req, draft_id="draft-A")
        self.assertEqual(result.tier, 2)
        self.assertTrue(result.is_trial)
        self.assertEqual(result.uses_remaining, 0)

    def test_exhausted_code_with_new_draft_id_denied(self):
        code = _make_code(raw="FULLCODE", max_uses=2)
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-1")
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-2")
        req = _make_request(code_header="FULLCODE")
        result = resolve_access(req, draft_id="draft-new")
        self.assertEqual(result.tier, 0)
        self.assertIsNone(result.code)

    def test_exhausted_code_without_draft_id_denied(self):
        code = _make_code(raw="FULLCODE2", max_uses=1)
        AccessCodeUse.objects.create(access_code=code, draft_id="draft-X")
        req = _make_request(code_header="FULLCODE2")
        result = resolve_access(req)
        self.assertEqual(result.tier, 0)

    def test_unlimited_code_returns_none_uses_remaining(self):
        _make_code(raw="UNLIMITED", max_uses=None)
        req = _make_request(code_header="UNLIMITED")
        result = resolve_access(req)
        self.assertTrue(result.is_trial)
        self.assertIsNone(result.uses_remaining)

    def test_expired_code_denied(self):
        _make_code(raw="EXPCODE", expires_at=timezone.now() - timedelta(hours=1))
        req = _make_request(code_header="EXPCODE")
        result = resolve_access(req)
        self.assertEqual(result.tier, 0)
        self.assertIsNone(result.code)

    def test_inactive_code_denied(self):
        _make_code(raw="INACTCODE", is_active=False)
        req = _make_request(code_header="INACTCODE")
        result = resolve_access(req)
        self.assertEqual(result.tier, 0)

    def test_wrong_code_denied(self):
        _make_code(raw="RIGHTCODE")
        req = _make_request(code_header="WRONGCODE")
        result = resolve_access(req)
        self.assertEqual(result.tier, 0)

    def test_non_dict_request_data_does_not_crash(self):
        req = _make_request()
        req.data = "not-a-dict"
        result = resolve_access(req)
        self.assertEqual(result.tier, 0)

    def test_upgrade_kind_code_not_matched_anonymously(self):
        _make_code(raw="UPGRADECODE", kind=AccessCode.KIND_UPGRADE, tier=2)
        req = _make_request(code_header="UPGRADECODE")
        result = resolve_access(req)
        self.assertEqual(result.tier, 0)
        self.assertIsNone(result.code)

    def test_trial_kind_forced_to_tier_2_regardless_of_requested_tier(self):
        code = _make_code(raw="FORCEDCODE", tier=1)
        self.assertEqual(code.tier, 2)


@tag("db")
class NoCredentialsTest(TestCase):
    def test_no_credentials_returns_tier_0(self):
        req = _make_request()
        result = resolve_access(req)
        self.assertEqual(result, AccessResult(0, None, False, None, None, None))


# ---------------------------------------------------------------------------
# GET /broadcast/access endpoint tests
# ---------------------------------------------------------------------------

EVENT = {
    "title": "Dance Night",
    "description": "Social dancing.",
    "start_datetime": "2026-07-10T19:00:00-04:00",
    "venue_name": "The Plant",
    "address_line1": "220 Lorax Ln",
    "city": "Pittsboro",
    "state": "NC",
    "zip": "27312",
    "locality": ["pittsboro"],
    "categories": ["music"],
}


def _patch_jwt(claims):
    return mock.patch("broadcast.access.verify_better_auth_jwt", return_value=claims)


@override_settings(RATELIMIT_ENABLE=False)
@tag("db")
class AccessInfoEndpointTest(TestCase):
    """Tests for GET /broadcast/access — four semantic cases plus code path."""

    def setUp(self):
        self.client = APIClient()

    def test_no_credentials_returns_200_tier_0(self):
        resp = self.client.get("/broadcast/access")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 0)
        self.assertFalse(body["is_trial"])
        self.assertIsNone(body["uses_remaining"])

    def test_valid_jwt_no_grant_returns_200_tier_0(self):
        with _patch_jwt({"email": "nobody@example.com"}):
            resp = self.client.get(
                "/broadcast/access",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["tier"], 0)

    def test_valid_jwt_with_grant_returns_200_tier(self):
        BroadcastAccess.objects.create(email="alice@example.com", tier=2)
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.get(
                "/broadcast/access",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 2)
        self.assertFalse(body["is_trial"])
        self.assertIsNone(body["uses_remaining"])

    def test_invalid_jwt_returns_403(self):
        with _patch_jwt(None):
            resp = self.client.get(
                "/broadcast/access",
                HTTP_AUTHORIZATION="Bearer badtoken",
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Invalid credentials.")

    def test_invalid_code_header_returns_403(self):
        resp = self.client.get(
            "/broadcast/access",
            HTTP_X_BROADCAST_ACCESS_CODE="NOSUCHCODE",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Invalid credentials.")

    def test_valid_code_returns_200_with_trial_info(self):
        _make_code(raw="INFOCODE", max_uses=3)
        resp = self.client.get(
            "/broadcast/access",
            HTTP_X_BROADCAST_ACCESS_CODE="INFOCODE",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 2)
        self.assertTrue(body["is_trial"])
        self.assertEqual(body["uses_remaining"], 3)


# ---------------------------------------------------------------------------
# Preview metering tests
# ---------------------------------------------------------------------------


@override_settings(RATELIMIT_ENABLE=False)
@tag("db")
class PreviewMeteringTest(TestCase):
    """Metering: AccessCodeUse rows created/reused in preview for trial codes."""

    def setUp(self):
        self.client = APIClient()
        self.code = _make_code(raw="TRIALCODE", max_uses=3)

    def _preview(self, draft_id=None, code="TRIALCODE"):
        body = {"access_code": code, "event": EVENT}
        if draft_id is not None:
            body["draft_id"] = draft_id
        return self.client.post("/broadcast/preview", body, format="json")

    def test_trial_preview_without_draft_id_returns_400(self):
        resp = self._preview(draft_id=None)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("draft_id", resp.json())

    def test_trial_preview_creates_one_use_row(self):
        resp = self._preview(draft_id="draft-1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AccessCodeUse.objects.filter(access_code=self.code).count(), 1)

    def test_re_preview_same_draft_is_idempotent(self):
        self._preview(draft_id="draft-1")
        resp = self._preview(draft_id="draft-1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AccessCodeUse.objects.filter(access_code=self.code).count(), 1)

    def test_fourth_distinct_draft_on_3_use_code_denied(self):
        for i in range(1, 4):
            self._preview(draft_id=f"draft-{i}")
        # Code is now exhausted (3/3 uses consumed)
        resp = self._preview(draft_id="draft-4")
        self.assertEqual(resp.status_code, 403)

    def test_fourth_call_with_already_counted_draft_allowed(self):
        for i in range(1, 4):
            self._preview(draft_id=f"draft-{i}")
        # Re-previewing an already-counted draft is allowed even when exhausted
        resp = self._preview(draft_id="draft-1")
        self.assertEqual(resp.status_code, 200)

    def test_non_trial_jwt_preview_needs_no_draft_id(self):
        BroadcastAccess.objects.create(email="legit@example.com", tier=1)
        with _patch_jwt({"email": "legit@example.com"}):
            resp = self.client.post(
                "/broadcast/preview",
                {"event": EVENT},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AccessCodeUse.objects.count(), 0)


# ---------------------------------------------------------------------------
# redeem_upgrade_code() — authenticated, account-permanent redemption
# ---------------------------------------------------------------------------


def _make_upgrade_code(
    label="acme-co", tier=2, max_uses=3, is_active=True, expires_at=None, raw="UPGRADERAW"
):
    return AccessCode.objects.create(
        code_hash=hash_code(raw),
        label=label,
        kind=AccessCode.KIND_UPGRADE,
        tier=tier,
        max_uses=max_uses,
        is_active=is_active,
        expires_at=expires_at,
    )


@tag("db")
class RedeemUpgradeCodeTest(TestCase):
    def test_valid_code_sets_permanent_tier(self):
        _make_upgrade_code(raw="RAW1", tier=2)
        new_tier = redeem_upgrade_code("alice@example.com", "RAW1")
        self.assertEqual(new_tier, 2)
        grant = BroadcastAccess.objects.get(email="alice@example.com")
        self.assertEqual(grant.tier, 2)

    def test_overwrites_existing_grant(self):
        BroadcastAccess.objects.create(email="alice@example.com", tier=1)
        _make_upgrade_code(raw="RAW2", tier=2)
        redeem_upgrade_code("alice@example.com", "RAW2")
        grant = BroadcastAccess.objects.get(email="alice@example.com")
        self.assertEqual(grant.tier, 2)

    def test_records_redemption(self):
        code = _make_upgrade_code(raw="RAW3")
        redeem_upgrade_code("alice@example.com", "RAW3")
        self.assertTrue(
            AccessCodeRedemption.objects.filter(
                access_code=code, email="alice@example.com"
            ).exists()
        )

    def test_same_email_redeeming_twice_does_not_consume_extra_slot(self):
        code = _make_upgrade_code(raw="RAW4", max_uses=1)
        first = redeem_upgrade_code("alice@example.com", "RAW4")
        second = redeem_upgrade_code("alice@example.com", "RAW4")
        self.assertEqual(first, 2)
        self.assertEqual(second, 2)
        self.assertEqual(code.redemptions.count(), 1)

    def test_max_uses_exhausted_denies_new_email(self):
        _make_upgrade_code(raw="RAW5", max_uses=1)
        redeem_upgrade_code("alice@example.com", "RAW5")
        result = redeem_upgrade_code("bob@example.com", "RAW5")
        self.assertIsNone(result)
        self.assertFalse(BroadcastAccess.objects.filter(email="bob@example.com").exists())

    def test_unlimited_max_uses_allows_many_emails(self):
        _make_upgrade_code(raw="RAW6", max_uses=None)
        self.assertEqual(redeem_upgrade_code("a@example.com", "RAW6"), 2)
        self.assertEqual(redeem_upgrade_code("b@example.com", "RAW6"), 2)

    def test_expired_code_denied(self):
        _make_upgrade_code(raw="RAW7", expires_at=timezone.now() - timedelta(hours=1))
        result = redeem_upgrade_code("alice@example.com", "RAW7")
        self.assertIsNone(result)
        self.assertFalse(BroadcastAccess.objects.filter(email="alice@example.com").exists())

    def test_inactive_code_denied(self):
        _make_upgrade_code(raw="RAW8", is_active=False)
        result = redeem_upgrade_code("alice@example.com", "RAW8")
        self.assertIsNone(result)

    def test_wrong_code_denied(self):
        _make_upgrade_code(raw="RAW9")
        result = redeem_upgrade_code("alice@example.com", "WRONGCODE")
        self.assertIsNone(result)

    def test_trial_kind_code_not_redeemable_as_upgrade(self):
        _make_code(raw="TRIALRAW")  # kind=trial by default
        result = redeem_upgrade_code("alice@example.com", "TRIALRAW")
        self.assertIsNone(result)
        self.assertFalse(BroadcastAccess.objects.filter(email="alice@example.com").exists())


# ---------------------------------------------------------------------------
# POST /broadcast/redeem endpoint
# ---------------------------------------------------------------------------


@override_settings(RATELIMIT_ENABLE=False)
@tag("db")
class RedeemEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_requires_login(self):
        _make_upgrade_code(raw="EPRAW1")
        resp = self.client.post("/broadcast/redeem", {"access_code": "EPRAW1"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_access_code_via_header_without_jwt_is_rejected(self):
        # Anonymous access-code auth doesn't satisfy RequiresBroadcastLogin.
        _make_upgrade_code(raw="EPRAW2")
        resp = self.client.post(
            "/broadcast/redeem",
            {"access_code": "EPRAW2"},
            format="json",
            HTTP_X_BROADCAST_ACCESS_CODE="EPRAW2",
        )
        self.assertEqual(resp.status_code, 403)

    def test_valid_jwt_and_code_upgrades_tier(self):
        _make_upgrade_code(raw="EPRAW3", tier=2)
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/redeem",
                {"access_code": "EPRAW3"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["tier"], 2)
        self.assertEqual(BroadcastAccess.objects.get(email="alice@example.com").tier, 2)

    def test_missing_access_code_returns_400(self):
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/redeem",
                {},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_code_returns_403(self):
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/redeem",
                {"access_code": "NOPE"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 403)

    def test_trial_code_rejected_via_redeem_endpoint(self):
        _make_code(raw="EPTRIAL")  # kind=trial by default
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/redeem",
                {"access_code": "EPTRIAL"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 403)

    def test_upgrade_tier2_redemption_survives_reload_via_jwt_path(self):
        """Regression for 26.2: redeeming a real --kind upgrade --tier 2 code must
        permanently set BroadcastAccess.tier, and a *later, separate* request on the
        JWT path (GET /broadcast/access, simulating a page reload) must read that same
        tier back — including when the email claim's casing differs between the two
        requests (write path lowercases via request.broadcast_email /
        authenticated_email; read path must do the same on the JWT claim)."""
        _make_upgrade_code(raw="RELOADRAW", tier=2)

        # Step 1: logged-in user redeems the upgrade code (JWT claim uppercase).
        with _patch_jwt({"email": "UPPER@Example.com"}):
            redeem_resp = self.client.post(
                "/broadcast/redeem",
                {"access_code": "RELOADRAW"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(redeem_resp.status_code, 200)
        self.assertEqual(redeem_resp.json()["tier"], 2)

        # BroadcastAccess row is permanent, keyed by lowercased email.
        grant = BroadcastAccess.objects.get(email="upper@example.com")
        self.assertEqual(grant.tier, 2)

        # Step 2: a brand new request (simulating reload) hits the JWT read path with
        # a differently-cased email claim — must still resolve to tier 2, not tier 0.
        with _patch_jwt({"email": "Upper@EXAMPLE.com"}):
            reload_resp = self.client.get(
                "/broadcast/access",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(reload_resp.status_code, 200)
        body = reload_resp.json()
        self.assertEqual(body["tier"], 2)
        self.assertFalse(body["is_trial"])


# ---------------------------------------------------------------------------
# bind_trial_code — TRIAL codes bound to an account (no re-entry on next login)
# ---------------------------------------------------------------------------


@tag("db")
class BindTrialCodeTest(TestCase):
    def setUp(self):
        # resolve_access()'s JWT-permanent-tier lookup is process-cached
        # (ACCESS_TTL) — clear it so an unrelated earlier test's cached entry
        # for the same email can't leak into these assertions.
        django_cache.clear()

    def test_valid_code_creates_redemption_and_returns_result(self):
        code = _make_code(raw="BINDRAW1")
        result = bind_trial_code("alice@example.com", "BINDRAW1")
        self.assertIsInstance(result, AccessResult)
        self.assertEqual(result.tier, 2)
        self.assertTrue(result.is_trial)
        self.assertTrue(
            AccessCodeRedemption.objects.filter(
                access_code=code, email="alice@example.com"
            ).exists()
        )

    def test_lowercases_email(self):
        _make_code(raw="BINDRAW2")
        bind_trial_code("Alice@Example.com", "BINDRAW2")
        self.assertTrue(AccessCodeRedemption.objects.filter(email="alice@example.com").exists())

    def test_never_writes_broadcast_access(self):
        # Binding a TRIAL code must stay temporary — it should never create a
        # permanent BroadcastAccess grant the way redeem_upgrade_code does.
        _make_code(raw="BINDRAW3")
        bind_trial_code("alice@example.com", "BINDRAW3")
        self.assertFalse(BroadcastAccess.objects.filter(email="alice@example.com").exists())

    def test_idempotent_rebind_same_email(self):
        code = _make_code(raw="BINDRAW4")
        bind_trial_code("alice@example.com", "BINDRAW4")
        bind_trial_code("alice@example.com", "BINDRAW4")
        self.assertEqual(
            AccessCodeRedemption.objects.filter(
                access_code=code, email="alice@example.com"
            ).count(),
            1,
        )

    def test_expired_code_denied(self):
        _make_code(raw="BINDRAW5", expires_at=timezone.now() - timedelta(hours=1))
        result = bind_trial_code("alice@example.com", "BINDRAW5")
        self.assertIsNone(result)
        self.assertFalse(AccessCodeRedemption.objects.filter(email="alice@example.com").exists())

    def test_upgrade_kind_code_not_bindable_as_trial(self):
        _make_upgrade_code(raw="BINDRAW6")
        result = bind_trial_code("alice@example.com", "BINDRAW6")
        self.assertIsNone(result)

    def test_wrong_code_denied(self):
        _make_code(raw="BINDRAW7")
        result = bind_trial_code("alice@example.com", "WRONGCODE")
        self.assertIsNone(result)

    def test_bound_code_resolves_via_jwt_without_headers(self):
        """The core fix: once bound, resolve_access() over the JWT alone (no
        access-code header, simulating a fresh login on any device) restores
        trial access — no re-entry, no localStorage needed."""
        _make_code(raw="BINDRAW8", max_uses=None)
        bind_trial_code("alice@example.com", "BINDRAW8")

        req = _make_request(auth_header="Bearer faketoken")
        with _patch_jwt({"email": "alice@example.com"}):
            result = resolve_access(req)

        self.assertEqual(result.tier, 2)
        self.assertTrue(result.is_trial)

    def test_expired_bound_code_no_longer_resolves_via_jwt(self):
        code = _make_code(raw="BINDRAW9", max_uses=None)
        bind_trial_code("alice@example.com", "BINDRAW9")
        code.expires_at = timezone.now() - timedelta(hours=1)
        code.save()

        req = _make_request(auth_header="Bearer faketoken")
        with _patch_jwt({"email": "alice@example.com"}):
            result = resolve_access(req)

        self.assertEqual(result.tier, 0)

    def test_permanent_grant_takes_priority_over_bound_trial(self):
        BroadcastAccess.objects.create(email="alice@example.com", tier=1)
        _make_code(raw="BINDRAW10", tier=2, max_uses=None)
        bind_trial_code("alice@example.com", "BINDRAW10")

        req = _make_request(auth_header="Bearer faketoken")
        with _patch_jwt({"email": "alice@example.com"}):
            result = resolve_access(req)

        self.assertEqual(result.tier, 1)
        self.assertFalse(result.is_trial)


# ---------------------------------------------------------------------------
# POST /broadcast/verify-code endpoint
# ---------------------------------------------------------------------------


@override_settings(RATELIMIT_ENABLE=False)
@tag("db")
class VerifyCodeEndpointTest(TestCase):
    def setUp(self):
        django_cache.clear()
        self.client = APIClient()

    def test_requires_login(self):
        _make_code(raw="VCRAW1")
        resp = self.client.post("/broadcast/verify-code", {"access_code": "VCRAW1"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_upgrade_code_sets_permanent_tier(self):
        _make_upgrade_code(raw="VCRAW2", tier=2)
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/verify-code",
                {"access_code": "VCRAW2"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 2)
        self.assertFalse(body["is_trial"])
        self.assertEqual(BroadcastAccess.objects.get(email="alice@example.com").tier, 2)

    def test_trial_code_binds_to_account(self):
        _make_code(raw="VCRAW3", max_uses=None)
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/verify-code",
                {"access_code": "VCRAW3"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 2)
        self.assertTrue(body["is_trial"])
        self.assertTrue(AccessCodeRedemption.objects.filter(email="alice@example.com").exists())
        self.assertFalse(BroadcastAccess.objects.filter(email="alice@example.com").exists())

    def test_trial_code_survives_relogin_with_no_code_resent(self):
        """End-to-end regression: verify a trial code once, then a later,
        separate request presenting only the JWT (simulating logout/login,
        even on a different browser with empty localStorage) must still
        resolve full access — the original bug report."""
        _make_code(raw="VCRAW4", max_uses=None)
        with _patch_jwt({"email": "alice@example.com"}):
            verify_resp = self.client.post(
                "/broadcast/verify-code",
                {"access_code": "VCRAW4"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(verify_resp.status_code, 200)

        with _patch_jwt({"email": "alice@example.com"}):
            relogin_resp = self.client.get(
                "/broadcast/access",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(relogin_resp.status_code, 200)
        body = relogin_resp.json()
        self.assertEqual(body["tier"], 2)
        self.assertTrue(body["is_trial"])

    def test_invalid_code_returns_403(self):
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/verify-code",
                {"access_code": "NOPE"},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 403)

    def test_missing_access_code_returns_400(self):
        with _patch_jwt({"email": "alice@example.com"}):
            resp = self.client.post(
                "/broadcast/verify-code",
                {},
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 400)
