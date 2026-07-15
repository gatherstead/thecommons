"""DB-backed broadcast access resolution.

JWT path: Authorization: Bearer → email claim → BroadcastAccess tier.
Code path: X-Broadcast-Access-Code header or body access_code → TRIAL AccessCode
row only (anonymous, no account). UPGRADE AccessCode rows are never resolved
here — they're redeemed by a logged-in user via redeem_upgrade_code(), which
permanently sets BroadcastAccess.tier instead of granting a per-request tier.
No credentials → tier 0. resolve_access is read-only; callers write AccessCodeUse.
"""

import hashlib
import hmac
from dataclasses import dataclass, field

from django.utils import timezone

from backend.jwt_auth import verify_better_auth_jwt
from broadcast import cache as access_cache
from broadcast.models import AccessCode, AccessCodeRedemption, BroadcastAccess

# ---------------------------------------------------------------------------
# DB-backed access layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessResult:
    tier: int
    identity: str | None
    is_trial: bool
    uses_remaining: int | None
    client_label: str | None
    code: AccessCode | None = field(default=None)


def hash_code(raw: str) -> str:
    """SHA-256 hexdigest of a raw access code (never store raw)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def authenticated_email(request) -> str | None:
    """Verify an Authorization: Bearer JWT and return its lowercased email claim.

    Returns None on any failure (no header, invalid token, missing claim) —
    callers that need to distinguish "no JWT" from "invalid JWT" should check
    the Authorization header themselves first.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    claims = verify_better_auth_jwt(auth_header[7:])
    if claims is None:
        return None
    email = claims.get("email")
    return email.lower() if email else None


def _trial_liveness(code: AccessCode, draft_id: str | None, now) -> tuple[bool, int | None]:
    """Live expiry + max_uses check for a TRIAL code. Returns (ok, uses_remaining).

    Shared by the anonymous code path and the account-bound path below, so
    both honor the same expiry/metering rules. Never cached — consumption
    counts must always be live (see cache.py docstring).
    """
    if code.expires_at is not None and code.expires_at < now:
        return False, None
    used = code.uses.count()
    if code.max_uses is None:
        return True, None
    uses_remaining = max(code.max_uses - used, 0)
    if used >= code.max_uses:
        already_counted = draft_id is not None and code.uses.filter(draft_id=draft_id).exists()
        if not already_counted:
            return False, uses_remaining
    return True, uses_remaining


def _resolve_bound_trial(email: str, draft_id: str | None, now) -> AccessResult | None:
    """An account-bound TRIAL code (see bind_trial_code) resolved via JWT.

    Lets a TRIAL code survive logout/login — and travel across devices —
    without the client persisting or re-entering it, the same way an UPGRADE
    code's permanent tier already does. Unlike UPGRADE, this stays temporary:
    it never writes BroadcastAccess and expires when the code does.
    """
    redemption = (
        AccessCodeRedemption.objects.filter(
            email=email, access_code__kind=AccessCode.KIND_TRIAL, access_code__is_active=True
        )
        .select_related("access_code")
        .order_by("-created_at")
        .first()
    )
    if redemption is None:
        return None
    code = redemption.access_code
    ok, uses_remaining = _trial_liveness(code, draft_id, now)
    if not ok:
        return None
    return AccessResult(
        tier=code.tier,
        identity=email,
        is_trial=True,
        uses_remaining=uses_remaining,
        client_label=code.label,
        code=code,
    )


def resolve_access(request, draft_id: str | None = None) -> AccessResult:  # noqa: C901  # tiered auth resolution; complexity is inherent
    """Resolve tiered access from a request.

    Resolution order:
      1. Authorization: Bearer <jwt>  → JWT path: BroadcastAccess permanent
         tier, falling back to an account-bound TRIAL code (see
         bind_trial_code) if there's no permanent grant.
      2. X-Broadcast-Access-Code header or request.data["access_code"] →
         anonymous TRIAL code path (not yet bound to any account)
      3. No credentials → tier 0, no identity

    Read-only — never creates AccessCodeUse rows.
    """
    # ------------------------------------------------------------------
    # Step 1: JWT path
    # ------------------------------------------------------------------
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        email = authenticated_email(request)
        if email:
            cached = access_cache.get_jwt_access(email)
            if cached is None:
                try:
                    grant = BroadcastAccess.objects.get(email=email)
                    tier = grant.tier
                except BroadcastAccess.DoesNotExist:
                    tier = 0
                cached = {"tier": tier, "identity": email, "client_label": email}
                access_cache.set_jwt_access(email, cached)
            if cached["tier"] > 0:
                return AccessResult(
                    tier=cached["tier"],
                    identity=cached["identity"],
                    is_trial=False,
                    uses_remaining=None,
                    client_label=cached["client_label"],
                    code=None,
                )
            bound = _resolve_bound_trial(email, draft_id, timezone.now())
            if bound is not None:
                return bound
            return AccessResult(
                tier=0,
                identity=cached["identity"],
                is_trial=False,
                uses_remaining=None,
                client_label=cached["client_label"],
                code=None,
            )
        # JWT present (valid or invalid) but unusable → no access, skip code path
        return AccessResult(0, None, False, None, None, None)

    # ------------------------------------------------------------------
    # Step 2: Access code path — TRIAL codes only (anonymous, no account)
    # ------------------------------------------------------------------
    raw_code = request.headers.get("X-Broadcast-Access-Code")
    if raw_code is None:
        data = getattr(request, "data", None)
        if isinstance(data, dict):
            raw_code = data.get("access_code")

    if raw_code and isinstance(raw_code, str):
        incoming_hash = hash_code(raw_code)
        now = timezone.now()

        cached_meta = access_cache.get_code_meta(incoming_hash)
        matched = None
        if cached_meta is None:
            for code in AccessCode.objects.filter(is_active=True, kind=AccessCode.KIND_TRIAL):
                if hmac.compare_digest(code.code_hash, incoming_hash):
                    matched = code
            if matched is not None:
                access_cache.set_code_meta(
                    incoming_hash,
                    {
                        "code_id": matched.id,
                        "tier": matched.tier,
                        "label": matched.label,
                        "max_uses": matched.max_uses,
                        "expires_at": matched.expires_at.isoformat()
                        if matched.expires_at is not None
                        else None,
                    },
                )
        else:
            # Identity is cached, but uses()/max_uses enforcement must always be
            # live — fetch the row to run the same count/expiry checks as a miss.
            matched = AccessCode.objects.filter(id=cached_meta["code_id"]).first()

        if matched is not None:
            ok, uses_remaining = _trial_liveness(matched, draft_id, now)
            if not ok:
                return AccessResult(0, None, False, None, None, None)

            label = matched.label
            return AccessResult(
                tier=matched.tier,
                identity=label,
                is_trial=True,
                uses_remaining=uses_remaining,
                client_label=label,
                code=matched,
            )

    # ------------------------------------------------------------------
    # Step 3: No usable credentials
    # ------------------------------------------------------------------
    return AccessResult(0, None, False, None, None, None)


def redeem_upgrade_code(email: str, raw_code: str) -> int | None:
    """Redeem an UPGRADE-kind code against a logged-in user's permanent tier.

    Always overwrites BroadcastAccess.tier with the code's tier (last code
    entered wins — deliberately simple so support/sales can just say "enter
    this code" without worrying about downgrade edge cases). Redemption is
    idempotent per email: re-entering the same code doesn't consume another
    max_uses slot. TRIAL codes are never accepted here.

    Returns the new tier, or None if the code is invalid/inactive/expired/exhausted.
    """
    incoming_hash = hash_code(raw_code)
    now = timezone.now()

    matched = None
    for code in AccessCode.objects.filter(is_active=True, kind=AccessCode.KIND_UPGRADE):
        if hmac.compare_digest(code.code_hash, incoming_hash):
            matched = code

    if matched is None:
        return None
    if matched.expires_at is not None and matched.expires_at < now:
        return None

    already_redeemed = matched.redemptions.filter(email=email).exists()
    if not already_redeemed and matched.max_uses is not None:
        if matched.redemptions.count() >= matched.max_uses:
            return None

    BroadcastAccess.objects.update_or_create(email=email, defaults={"tier": matched.tier})
    AccessCodeRedemption.objects.get_or_create(access_code=matched, email=email)
    access_cache.invalidate_jwt_access(email)
    return matched.tier


def bind_trial_code(email: str, raw_code: str, draft_id: str | None = None) -> AccessResult | None:
    """Bind a TRIAL code to a logged-in account, called from POST /broadcast/verify-code.

    Unlike redeem_upgrade_code, this never writes BroadcastAccess — trial
    access stays temporary and expires with the code, it just no longer
    requires the client to hold the raw code (localStorage) to keep it: once
    bound, _resolve_bound_trial() resolves it straight from the JWT on any
    device, so logout/login (or a new browser) doesn't need re-entry.
    Idempotent per email via AccessCodeRedemption's unique_together.

    Returns the resolved AccessResult, or None if the code is
    invalid/inactive/expired/exhausted.
    """
    email = email.lower()
    incoming_hash = hash_code(raw_code)
    now = timezone.now()

    matched = None
    for code in AccessCode.objects.filter(is_active=True, kind=AccessCode.KIND_TRIAL):
        if hmac.compare_digest(code.code_hash, incoming_hash):
            matched = code

    if matched is None:
        return None

    ok, uses_remaining = _trial_liveness(matched, draft_id, now)
    if not ok:
        return None

    AccessCodeRedemption.objects.get_or_create(access_code=matched, email=email)
    return AccessResult(
        tier=matched.tier,
        identity=email,
        is_trial=True,
        uses_remaining=uses_remaining,
        client_label=matched.label,
        code=matched,
    )
