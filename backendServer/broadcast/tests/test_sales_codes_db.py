"""DB-tier tests for broadcast.sales_codes and the AccessCode admin's sales dashboard.

Run with:
    DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test \
        broadcast.tests.test_sales_codes_db
"""

from django.contrib.auth.models import User
from django.test import TestCase, tag
from django.urls import reverse

from broadcast.access import resolve_access
from broadcast.models import AccessCode, SalesCodeSlot
from broadcast.sales_codes import ensure_sales_slots, rotate_sales_slot


@tag("db")
class RotateSalesSlotTest(TestCase):
    def test_creates_correct_kind_and_tier_per_slot(self):
        trial = rotate_sales_slot(SalesCodeSlot.SLOT_TRIAL)
        tier1 = rotate_sales_slot(SalesCodeSlot.SLOT_TIER1)
        tier2 = rotate_sales_slot(SalesCodeSlot.SLOT_TIER2)

        self.assertEqual(trial.access_code.kind, AccessCode.KIND_TRIAL)
        self.assertEqual(trial.access_code.tier, 2)
        self.assertIsNotNone(trial.access_code.expires_at)

        self.assertEqual(tier1.access_code.kind, AccessCode.KIND_UPGRADE)
        self.assertEqual(tier1.access_code.tier, 1)
        self.assertIsNone(tier1.access_code.expires_at)

        self.assertEqual(tier2.access_code.kind, AccessCode.KIND_UPGRADE)
        self.assertEqual(tier2.access_code.tier, 2)

    def test_raw_code_resolves_via_resolve_access_for_trial(self):
        from django.test import RequestFactory

        slot = rotate_sales_slot(SalesCodeSlot.SLOT_TRIAL)
        factory = RequestFactory()
        req = factory.post("/", HTTP_X_BROADCAST_ACCESS_CODE=slot.raw_code)
        req.data = {}
        result = resolve_access(req)
        self.assertEqual(result.tier, 2)
        self.assertTrue(result.is_trial)

    def test_rotation_creates_new_code_and_old_stays_active(self):
        first = rotate_sales_slot(SalesCodeSlot.SLOT_TIER1)
        first_code = first.access_code
        second = rotate_sales_slot(SalesCodeSlot.SLOT_TIER1)

        self.assertNotEqual(first.raw_code, second.raw_code)
        self.assertNotEqual(first_code.id, second.access_code.id)

        first_code.refresh_from_db()
        self.assertTrue(first_code.is_active)  # old code is left usable, not revoked

    def test_only_one_slot_row_per_slot_key(self):
        rotate_sales_slot(SalesCodeSlot.SLOT_TRIAL)
        rotate_sales_slot(SalesCodeSlot.SLOT_TRIAL)
        rotate_sales_slot(SalesCodeSlot.SLOT_TRIAL)
        self.assertEqual(SalesCodeSlot.objects.filter(slot=SalesCodeSlot.SLOT_TRIAL).count(), 1)


@tag("db")
class EnsureSalesSlotsTest(TestCase):
    def test_bootstraps_all_three_slots(self):
        self.assertEqual(SalesCodeSlot.objects.count(), 0)
        slots = ensure_sales_slots()
        self.assertEqual(len(slots), 3)
        self.assertEqual(SalesCodeSlot.objects.count(), 3)
        self.assertEqual(
            [s.slot for s in slots],
            [SalesCodeSlot.SLOT_TRIAL, SalesCodeSlot.SLOT_TIER1, SalesCodeSlot.SLOT_TIER2],
        )

    def test_idempotent_does_not_rotate_existing_slots(self):
        first = ensure_sales_slots()
        second = ensure_sales_slots()
        self.assertEqual(
            [s.raw_code for s in first],
            [s.raw_code for s in second],
        )


@tag("db")
class SalesDashboardAdminTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pw"
        )
        self.client.force_login(self.superuser)

    def test_changelist_renders_slot_cards(self):
        resp = self.client.get(reverse("admin:broadcast_accesscode_changelist"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Free trial", body)
        self.assertIn("Tier 1", body)
        self.assertIn("Tier 2", body)
        for slot in SalesCodeSlot.objects.all():
            self.assertIn(slot.raw_code, body)

    def test_rotate_endpoint_requires_staff(self):
        self.client.logout()
        url = reverse("admin:broadcast_accesscode_rotate_slot", args=[SalesCodeSlot.SLOT_TRIAL])
        resp = self.client.post(url)
        self.assertIn(resp.status_code, (302, 403))  # redirected to admin login

    def test_rotate_endpoint_rotates_and_returns_new_code(self):
        ensure_sales_slots()
        before = SalesCodeSlot.objects.get(slot=SalesCodeSlot.SLOT_TIER2).raw_code

        url = reverse("admin:broadcast_accesscode_rotate_slot", args=[SalesCodeSlot.SLOT_TIER2])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        after = resp.json()["raw_code"]
        self.assertNotEqual(before, after)
        self.assertEqual(SalesCodeSlot.objects.get(slot=SalesCodeSlot.SLOT_TIER2).raw_code, after)

    def test_rotate_endpoint_rejects_get(self):
        url = reverse("admin:broadcast_accesscode_rotate_slot", args=[SalesCodeSlot.SLOT_TRIAL])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)

    def test_rotate_endpoint_rejects_unknown_slot(self):
        url = reverse("admin:broadcast_accesscode_rotate_slot", args=["bogus"])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)
