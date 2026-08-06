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

from broadcast import cache as access_cache
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


def start_trial_clock(slot_obj: SalesCodeSlot) -> None:
    """Restart a trial code's expiry window from now — call when it's handed out.

    The dashboard mints the *next* code right after the current one is copied,
    so the code sitting in the box was created on the previous copy. Anchoring
    expiry to creation meant a slot nobody had touched for TRIAL_DAYS was
    handing out an already-dead code while the panel advertised "valid 3 days
    from when it's copied". The clock now genuinely starts at copy time.
    """
    code = slot_obj.access_code
    if code is None or code.kind != AccessCode.KIND_TRIAL:
        return
    code.expires_at = timezone.now() + timedelta(days=TRIAL_DAYS)
    code.save(update_fields=["expires_at", "updated_at"])
    access_cache.invalidate_code_meta(code.code_hash)


def ensure_sales_slots() -> list[SalesCodeSlot]:
    """Return all 3 slots in display order, creating any that don't exist yet.

    A trial slot whose pre-loaded code has already expired is rotated rather
    than displayed — belt-and-braces alongside start_trial_clock(), so the box
    can never show a dead code even if a rotation POST was lost.
    """
    existing = {s.slot: s for s in SalesCodeSlot.objects.select_related("access_code")}
    now = timezone.now()
    for slot_key, _label in SalesCodeSlot.SLOT_CHOICES:
        slot_obj = existing.get(slot_key)
        if slot_obj is None:
            existing[slot_key] = rotate_sales_slot(slot_key)
            continue
        code = slot_obj.access_code
        if code is not None and code.expires_at is not None and code.expires_at < now:
            existing[slot_key] = rotate_sales_slot(slot_key)
    return [existing[slot_key] for slot_key, _label in SalesCodeSlot.SLOT_CHOICES]
