"""DB-tier tests for broadcast management commands.

Run with:
    DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test \
        broadcast.tests.test_commands_db
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, tag
from django.utils import timezone

from broadcast.access import hash_code, resolve_access
from broadcast.models import AccessCode, BroadcastAccess


def _call(cmd, *args, **kwargs):
    """Invoke a management command and return captured stdout."""
    out = StringIO()
    call_command(cmd, *args, stdout=out, **kwargs)
    return out.getvalue()


def _make_request_with_code(raw_code):
    factory = RequestFactory()
    req = factory.post("/", HTTP_X_BROADCAST_ACCESS_CODE=raw_code)
    req.data = {}
    return req


# ---------------------------------------------------------------------------
# set_broadcast_access
# ---------------------------------------------------------------------------


@tag("db")
class SetBroadcastAccessTest(TestCase):
    def test_creates_new_row(self):
        out = _call("set_broadcast_access", "alice@example.com", "2")
        self.assertIn("none → 2", out)
        grant = BroadcastAccess.objects.get(email="alice@example.com")
        self.assertEqual(grant.tier, 2)

    def test_updates_existing_row(self):
        BroadcastAccess.objects.create(email="bob@example.com", tier=0)
        out = _call("set_broadcast_access", "bob@example.com", "1")
        self.assertIn("0 → 1", out)
        self.assertEqual(BroadcastAccess.objects.get(email="bob@example.com").tier, 1)

    def test_idempotent_same_tier(self):
        BroadcastAccess.objects.create(email="carol@example.com", tier=2)
        out = _call("set_broadcast_access", "carol@example.com", "2")
        self.assertIn("2 → 2", out)
        self.assertEqual(BroadcastAccess.objects.filter(email="carol@example.com").count(), 1)

    def test_case_insensitive_email_lowercased(self):
        out = _call("set_broadcast_access", "AryaV@UNC.EDU", "1")
        self.assertIn("none → 1", out)
        grant = BroadcastAccess.objects.get(email="aryav@unc.edu")
        self.assertEqual(grant.tier, 1)

    def test_case_insensitive_update(self):
        BroadcastAccess.objects.create(email="dave@example.com", tier=0)
        # Supply mixed-case — should hit the existing lowercased row.
        out = _call("set_broadcast_access", "Dave@Example.COM", "2")
        self.assertIn("0 → 2", out)
        self.assertEqual(BroadcastAccess.objects.filter(email="dave@example.com").count(), 1)


# ---------------------------------------------------------------------------
# generate_access_code
# ---------------------------------------------------------------------------


@tag("db")
class GenerateAccessCodeTest(TestCase):
    def test_raw_code_in_output(self):
        out = _call("generate_access_code")
        self.assertIn("Store it now", out)
        # The raw code block appears between "ACCESS CODE (copy now):" and "Store it now"
        self.assertIn("ACCESS CODE", out)

    def test_db_stores_hash_not_raw(self):
        _call("generate_access_code", label="hashtest")
        code = AccessCode.objects.get(label="hashtest")
        self.assertEqual(len(code.code_hash), 64)

    def test_default_kind_is_trial_tier_2_unlimited_uses_3_day_expiry(self):
        _call("generate_access_code", label="defaults")
        code = AccessCode.objects.get(label="defaults")
        self.assertEqual(code.kind, AccessCode.KIND_TRIAL)
        self.assertEqual(code.tier, 2)
        self.assertIsNone(code.max_uses)
        self.assertIsNotNone(code.expires_at)

    def test_trial_kind_rejects_explicit_non_default_tier(self):
        with self.assertRaises(CommandError):
            _call("generate_access_code", label="badtier", kind="trial", tier="1")

    def test_upgrade_kind_defaults_tier_2_uses_3_no_expiry(self):
        _call("generate_access_code", label="upgrade-defaults", kind="upgrade")
        code = AccessCode.objects.get(label="upgrade-defaults")
        self.assertEqual(code.kind, AccessCode.KIND_UPGRADE)
        self.assertEqual(code.tier, 2)
        self.assertEqual(code.max_uses, 3)
        self.assertIsNone(code.expires_at)

    def test_custom_tier_and_uses_requires_upgrade_kind(self):
        _call("generate_access_code", label="custom", kind="upgrade", tier="1", uses="5")
        code = AccessCode.objects.get(label="custom")
        self.assertEqual(code.kind, AccessCode.KIND_UPGRADE)
        self.assertEqual(code.tier, 1)
        self.assertEqual(code.max_uses, 5)

    def test_trial_days_sets_expiry_n_days_out(self):
        _call("generate_access_code", label="trialdays", trial_days="7")
        code = AccessCode.objects.get(label="trialdays")
        self.assertIsNotNone(code.expires_at)
        delta = code.expires_at - timezone.now()
        self.assertGreater(delta.days, 5)  # ~7 days, allowing for test runtime slack

    def test_trial_days_and_expires_mutually_exclusive(self):
        with self.assertRaises(CommandError):
            _call(
                "generate_access_code",
                label="conflict",
                trial_days="3",
                expires="2030-01-01T00:00:00",
            )

    def test_unlimited_flag_sets_null_max_uses(self):
        _call("generate_access_code", label="unlimited", unlimited=True)
        code = AccessCode.objects.get(label="unlimited")
        self.assertIsNone(code.max_uses)

    def test_uses_and_unlimited_mutually_exclusive(self):
        # Django's wrapped parser converts argparse errors to CommandError.
        with self.assertRaises(CommandError):
            call_command("generate_access_code", "--uses", "3", "--unlimited", stdout=StringIO())

    def test_expires_parsed_and_stored(self):
        _call("generate_access_code", label="expiring", expires="2030-01-01T00:00:00")
        code = AccessCode.objects.get(label="expiring")
        self.assertIsNotNone(code.expires_at)
        self.assertEqual(code.expires_at.year, 2030)

    def test_invalid_expires_raises_command_error(self):
        with self.assertRaises(CommandError):
            _call("generate_access_code", expires="not-a-date")

    def test_round_trip_resolve_access(self):
        """The raw code from generate output resolves to the correct tier via resolve_access."""
        out = _call("generate_access_code", label="roundtrip", tier="2", uses="5")

        # Extract the raw code from output (it's the indented line after "ACCESS CODE (copy now):")
        raw_code = None
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if "ACCESS CODE" in line and i + 1 < len(lines):
                raw_code = lines[i + 1].strip()
                break
        self.assertIsNotNone(raw_code, "Could not parse raw code from output")

        req = _make_request_with_code(raw_code)
        result = resolve_access(req)

        self.assertEqual(result.tier, 2)
        self.assertTrue(result.is_trial)
        self.assertEqual(result.uses_remaining, 5)
        self.assertEqual(result.identity, "roundtrip")

    def test_round_trip_unlimited_resolve_access(self):
        out = _call("generate_access_code", label="ultroundtrip", unlimited=True)

        raw_code = None
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if "ACCESS CODE" in line and i + 1 < len(lines):
                raw_code = lines[i + 1].strip()
                break
        self.assertIsNotNone(raw_code)

        req = _make_request_with_code(raw_code)
        result = resolve_access(req)

        self.assertTrue(result.is_trial)
        self.assertIsNone(result.uses_remaining)


# ---------------------------------------------------------------------------
# list_access_codes
# ---------------------------------------------------------------------------


@tag("db")
class ListAccessCodesTest(TestCase):
    def test_empty_db(self):
        out = _call("list_access_codes")
        self.assertIn("No access codes found", out)

    def test_lists_codes(self):
        AccessCode.objects.create(
            code_hash=hash_code("AAA"),
            label="partner",
            tier=2,
            max_uses=5,
        )
        out = _call("list_access_codes")
        self.assertIn("partner", out)
        self.assertIn("0/5", out)

    def test_unlimited_shows_infinity(self):
        AccessCode.objects.create(
            code_hash=hash_code("BBB"),
            label="unlim",
            tier=1,
            max_uses=None,
        )
        out = _call("list_access_codes")
        self.assertIn("∞", out)

    def test_no_label_shows_placeholder(self):
        AccessCode.objects.create(
            code_hash=hash_code("CCC"),
            label="",
            tier=0,
            max_uses=3,
        )
        out = _call("list_access_codes")
        self.assertIn("(no label)", out)

    def test_hash_prefix_not_full_hash(self):
        code = AccessCode.objects.create(
            code_hash=hash_code("DDD"),
            label="hashcheck",
            tier=2,
            max_uses=3,
        )
        out = _call("list_access_codes")
        # 8-char prefix appears
        self.assertIn(code.code_hash[:8], out)
        # full hash does not appear
        self.assertNotIn(code.code_hash, out)

    def test_active_and_inactive_shown(self):
        AccessCode.objects.create(
            code_hash=hash_code("EEE"), label="active-one", tier=2, max_uses=3
        )
        AccessCode.objects.create(
            code_hash=hash_code("FFF"), label="inactive-one", tier=2, max_uses=3, is_active=False
        )
        out = _call("list_access_codes")
        self.assertIn("active-one", out)
        self.assertIn("inactive-one", out)
        self.assertIn("yes", out)
        self.assertIn("no", out)


# ---------------------------------------------------------------------------
# revoke_access_code
# ---------------------------------------------------------------------------


@tag("db")
class RevokeAccessCodeTest(TestCase):
    def _make_code(self, label, raw="TESTRAW", tier=2):
        return AccessCode.objects.create(
            code_hash=hash_code(raw),
            label=label,
            tier=tier,
            max_uses=3,
        )

    def test_revoke_by_label(self):
        code = self._make_code("torevoke", raw="RAW1")
        out = _call("revoke_access_code", "torevoke")
        self.assertIn("Revoked", out)
        code.refresh_from_db()
        self.assertFalse(code.is_active)

    def test_revoke_by_id(self):
        code = self._make_code("byid", raw="RAW2")
        out = _call("revoke_access_code", str(code.id))
        self.assertIn("Revoked", out)
        code.refresh_from_db()
        self.assertFalse(code.is_active)

    def test_already_inactive_says_so(self):
        code = self._make_code("alreadydone", raw="RAW3")
        code.is_active = False
        code.save()
        out = _call("revoke_access_code", "alreadydone")
        self.assertIn("already inactive", out)
        # Still inactive
        code.refresh_from_db()
        self.assertFalse(code.is_active)

    def test_unknown_label_raises(self):
        with self.assertRaises(CommandError):
            _call("revoke_access_code", "nonexistent-label")

    def test_unknown_id_raises(self):
        with self.assertRaises(CommandError):
            _call("revoke_access_code", "99999")

    def test_ambiguous_label_errors_with_candidates(self):
        AccessCode.objects.create(code_hash=hash_code("RAW4"), label="shared", tier=2, max_uses=3)
        AccessCode.objects.create(code_hash=hash_code("RAW5"), label="shared", tier=1, max_uses=3)
        with self.assertRaises(CommandError) as ctx:
            _call("revoke_access_code", "shared")
        self.assertIn("shared", str(ctx.exception))
        self.assertIn("id=", str(ctx.exception))

    def test_revoked_code_stops_resolving(self):
        """After revocation, resolve_access returns tier 0."""
        raw = "REVOKEME"
        code = AccessCode.objects.create(
            code_hash=hash_code(raw),
            label="revtest",
            tier=2,
            max_uses=10,
        )
        # Confirm it resolves before revocation.
        req = _make_request_with_code(raw)
        result_before = resolve_access(req)
        self.assertEqual(result_before.tier, 2)

        _call("revoke_access_code", str(code.id))

        result_after = resolve_access(req)
        self.assertEqual(result_after.tier, 0)
        self.assertIsNone(result_after.code)
