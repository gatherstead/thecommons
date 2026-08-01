from unittest import mock

from django.test import TestCase, tag
from django.urls import reverse

from newsletter.models import NewsletterSubscriber


@tag("db")
class NewsletterSubscribeTests(TestCase):
    def setUp(self):
        # subscribe() now sends a welcome email; keep these tests off the network.
        patcher = mock.patch("newsletter.views.send_newsletter_welcome", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_subscribe_creates_subscriber(self):
        resp = self.client.post(
            reverse("subscribe"),
            {"email": "Reader@Example.com", "frequency": "MONTHLY"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["email"], "reader@example.com")
        self.assertEqual(resp.json()["frequency"], "MONTHLY")
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)

    def test_resubscribe_is_idempotent_and_updates_frequency(self):
        first = self.client.post(
            reverse("subscribe"),
            {"email": "reader@example.com", "frequency": "WEEKLY"},
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            reverse("subscribe"),
            {"email": "reader@example.com", "frequency": "MONTHLY"},
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["frequency"], "MONTHLY")
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)
        self.assertEqual(
            NewsletterSubscriber.objects.get(email="reader@example.com").frequency,
            "MONTHLY",
        )

    def test_missing_email_is_400(self):
        resp = self.client.post(
            reverse("subscribe"), {"frequency": "WEEKLY"}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "email is required")

    def test_subscribe_attempts_welcome_email_with_manage_link(self):
        with mock.patch("newsletter.views.send_newsletter_welcome") as welcome:
            resp = self.client.post(
                reverse("subscribe"),
                {"email": "reader@example.com", "frequency": "WEEKLY"},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 201)
        subscriber = NewsletterSubscriber.objects.get(email="reader@example.com")
        welcome.assert_called_once_with(subscriber.email, subscriber.manage_token)

    def test_subscribe_survives_welcome_send_failure(self):
        with mock.patch("newsletter.views.send_newsletter_welcome", return_value=False):
            resp = self.client.post(
                reverse("subscribe"),
                {"email": "reader@example.com", "frequency": "WEEKLY"},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 201)


@tag("db")
class NewsletterManageTests(TestCase):
    def setUp(self):
        self.subscriber = NewsletterSubscriber.objects.create(
            email="reader@example.com", frequency="WEEKLY", is_active=True
        )

    def test_get_returns_prefs_for_valid_token(self):
        resp = self.client.get(
            reverse("newsletter-manage"), {"token": str(self.subscriber.manage_token)}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["email"], "reader@example.com")
        self.assertEqual(body["frequency"], "WEEKLY")
        self.assertTrue(body["is_active"])

    def test_patch_changes_frequency(self):
        resp = self.client.patch(
            f"{reverse('newsletter-manage')}?token={self.subscriber.manage_token}",
            {"frequency": "MONTHLY"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["frequency"], "MONTHLY")
        self.subscriber.refresh_from_db()
        self.assertEqual(self.subscriber.frequency, "MONTHLY")
        self.assertTrue(self.subscriber.is_active)

    def test_patch_never_deactivates_without_deleting_row(self):
        resp = self.client.patch(
            f"{reverse('newsletter-manage')}?token={self.subscriber.manage_token}",
            {"frequency": "NEVER"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_active"])
        self.subscriber.refresh_from_db()
        self.assertFalse(self.subscriber.is_active)
        # Frequency is left as-is so a later re-subscribe can restore it.
        self.assertEqual(self.subscriber.frequency, "WEEKLY")
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)

    def test_unknown_token_is_404(self):
        unknown_token = "00000000-0000-0000-0000-000000000000"
        resp = self.client.get(reverse("newsletter-manage"), {"token": unknown_token})
        self.assertEqual(resp.status_code, 404)

    def test_malformed_token_is_404(self):
        resp = self.client.get(reverse("newsletter-manage"), {"token": "not-a-uuid"})
        self.assertEqual(resp.status_code, 404)

    def test_blank_token_is_404(self):
        resp = self.client.get(reverse("newsletter-manage"))
        self.assertEqual(resp.status_code, 404)

    def test_bad_frequency_is_400(self):
        resp = self.client.patch(
            f"{reverse('newsletter-manage')}?token={self.subscriber.manage_token}",
            {"frequency": "DAILY"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
