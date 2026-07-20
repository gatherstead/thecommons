from uuid import uuid4

from django.db import models

_TIER_CHOICES = [(0, "Tier 0"), (1, "Tier 1"), (2, "Tier 2")]


class BroadcastSubmission(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    client_label = models.CharField(max_length=64)
    title = models.CharField(max_length=300)
    description = models.TextField()
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    venue_name = models.CharField(max_length=200)
    address_line1 = models.CharField(max_length=200)
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=2, default="NC")
    zip = models.CharField(max_length=10)
    locality = models.JSONField(default=list)
    categories = models.JSONField(default=list)
    event_url = models.URLField(max_length=500, blank=True)
    ticket_url = models.URLField(max_length=500, blank=True)
    price = models.CharField(max_length=60, blank=True)
    is_free = models.BooleanField(default=False)
    image_url = models.URLField(max_length=500, blank=True)
    organizer_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, default="queued", choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.client_label}, {self.status})"


class BroadcastTarget(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In progress"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("needs_manual", "Needs manual"),
        ("skipped", "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    submission = models.ForeignKey(
        BroadcastSubmission, related_name="targets", on_delete=models.CASCADE
    )
    site_key = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default="pending", choices=STATUS_CHOICES)
    attempts = models.PositiveSmallIntegerField(default=0)
    external_url = models.URLField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    screenshot_path = models.CharField(max_length=300, blank=True)
    dry_run = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["submission", "site_key"], name="uniq_submission_site")
        ]

    def __str__(self):
        return f"{self.site_key}: {self.status}"


class BroadcastAccess(models.Model):
    email = models.CharField(max_length=254, unique=True)
    tier = models.IntegerField(choices=_TIER_CHOICES, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.email} (tier {self.tier})"

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)


class AccessCode(models.Model):
    """Two independent code pools, distinguished by `kind`.

    TRIAL codes are redeemed anonymously (no account) — see resolve_access()
    in access.py — and are always tier 2, time-boxed via expires_at rather
    than metered by uses. UPGRADE codes are redeemed only by a logged-in user
    via POST /broadcast/redeem and permanently set that account's
    BroadcastAccess.tier; they never touch the anonymous path.

    `code` is stored in plaintext so operators can copy a code after creation
    (e.g. to hand it to a user) — a deliberate convenience-over-defense-in-depth
    tradeoff for this low-stakes access gate. Validation never reads `code`;
    resolve_access()/redeem_upgrade_code() only ever compare against
    `code_hash`. Null for codes created before this field existed.
    """

    KIND_TRIAL = "trial"
    KIND_UPGRADE = "upgrade"
    KIND_CHOICES = [(KIND_TRIAL, "Trial (anonymous)"), (KIND_UPGRADE, "Upgrade (account)")]

    code = models.CharField(max_length=64, unique=True, null=True, blank=True)
    code_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=64)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_TRIAL)
    tier = models.IntegerField(choices=_TIER_CHOICES, default=2)
    max_uses = models.IntegerField(null=True, blank=True, default=3)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.label} ({self.kind}, tier {self.tier})"

    def save(self, *args, **kwargs):
        # Trial codes are always tier 2 — enforced here as the safety net
        # regardless of caller (admin form, management command, tests).
        if self.kind == self.KIND_TRIAL:
            self.tier = 2
        super().save(*args, **kwargs)


class AccessCodeUse(models.Model):
    """Meters a TRIAL code's anonymous preview usage, keyed by draft_id."""

    access_code = models.ForeignKey(AccessCode, related_name="uses", on_delete=models.CASCADE)
    draft_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("access_code", "draft_id")]

    def __str__(self):
        return f"{self.access_code.label} / {self.draft_id}"


class AccessCodeRedemption(models.Model):
    """One row per email that has redeemed an UPGRADE code — meters max_uses."""

    access_code = models.ForeignKey(
        AccessCode, related_name="redemptions", on_delete=models.CASCADE
    )
    email = models.CharField(max_length=254)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("access_code", "email")]

    def __str__(self):
        return f"{self.access_code.label} / {self.email}"

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)


class SalesCodeSlot(models.Model):
    """One evergreen, always-visible code per tier for the admin sales dashboard.

    Deliberately stores the raw code in plaintext (unlike AccessCode.code_hash
    elsewhere, which is hash-only and shown once) — these three slots exist so
    a salesperson can open the admin and always see a live, copyable code with
    no CLI involved. See broadcast/sales_codes.py for rotation.
    """

    SLOT_TRIAL = "trial"
    SLOT_TIER1 = "tier1"
    SLOT_TIER2 = "tier2"
    SLOT_CHOICES = [
        (SLOT_TRIAL, "Free trial"),
        (SLOT_TIER1, "Tier 1"),
        (SLOT_TIER2, "Tier 2"),
    ]
    # slot -> (AccessCode.kind, tier)
    SLOT_KIND_TIER = {
        SLOT_TRIAL: (AccessCode.KIND_TRIAL, 2),
        SLOT_TIER1: (AccessCode.KIND_UPGRADE, 1),
        SLOT_TIER2: (AccessCode.KIND_UPGRADE, 2),
    }

    slot = models.CharField(max_length=10, choices=SLOT_CHOICES, unique=True)
    access_code = models.OneToOneField(
        AccessCode, related_name="sales_slot", on_delete=models.PROTECT
    )
    raw_code = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_slot_display()} → {self.raw_code[:6]}…"
