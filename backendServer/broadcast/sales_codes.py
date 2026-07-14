"""Evergreen sales-facing access codes — see SalesCodeSlot in models.py.

These three slots keep the raw code on SalesCodeSlot.raw_code (in addition to
AccessCode.code) so the admin can always display a live, copyable code with
no CLI involved. Rotating creates a brand-new AccessCode and repoints the
slot at it — the old code is left active (not revoked), so anyone who
already has it keeps working.
"""

import secrets
from datetime import timedelta

from django.utils import timezone

from broadcast.access import hash_code
from broadcast.models import AccessCode, SalesCodeSlot

TRIAL_DAYS = 3


def rotate_sales_slot(slot: str) -> SalesCodeSlot:
    """Generate a fresh code for `slot` and repoint the slot at it."""
    kind, tier = SalesCodeSlot.SLOT_KIND_TIER[slot]
    raw = secrets.token_urlsafe(24)
    expires_at = (
        timezone.now() + timedelta(days=TRIAL_DAYS) if kind == AccessCode.KIND_TRIAL else None
    )

    code = AccessCode.objects.create(
        code=raw,
        code_hash=hash_code(raw),
        label=f"sales-{slot}",
        kind=kind,
        tier=tier,
        max_uses=None,  # shared/evergreen until the next rotation
        expires_at=expires_at,
    )
    slot_obj, _ = SalesCodeSlot.objects.update_or_create(
        slot=slot, defaults={"access_code": code, "raw_code": raw}
    )
    return slot_obj


def ensure_sales_slots() -> list[SalesCodeSlot]:
    """Return all 3 slots in display order, creating any that don't exist yet."""
    existing = {s.slot: s for s in SalesCodeSlot.objects.select_related("access_code")}
    for slot_key, _label in SalesCodeSlot.SLOT_CHOICES:
        if slot_key not in existing:
            existing[slot_key] = rotate_sales_slot(slot_key)
    return [existing[slot_key] for slot_key, _label in SalesCodeSlot.SLOT_CHOICES]
