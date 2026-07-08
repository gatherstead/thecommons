"""DB-backed broadcast access resolution.

JWT path: Authorization: Bearer → email claim → BroadcastAccess tier.
Code path: X-Broadcast-Access-Code header or body access_code → AccessCode row.
No credentials → tier 0. resolve_access is read-only; callers write AccessCodeUse.
"""

import hashlib
import hmac
from dataclasses import dataclass, field

from django.utils import timezone

from backend.jwt_auth import verify_better_auth_jwt
from broadcast.models import AccessCode, BroadcastAccess

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


def resolve_access(request, draft_id: str | None = None) -> AccessResult:  # noqa: C901  # tiered auth resolution; complexity is inherent
    """Resolve tiered access from a request.

    Resolution order:
      1. Authorization: Bearer <jwt>  → JWT path (verify claims, BroadcastAccess lookup)
      2. X-Broadcast-Access-Code header or request.data["access_code"] → code path
      3. No credentials → tier 0, no identity

    Read-only — never creates AccessCodeUse rows.
    """
    # ------------------------------------------------------------------
    # Step 1: JWT path
    # ------------------------------------------------------------------
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        claims = verify_better_auth_jwt(token)
        if claims is not None:
            email = claims.get("email")
            if email:
                email = email.lower()
                try:
                    grant = BroadcastAccess.objects.get(email=email)
                    tier = grant.tier
                except BroadcastAccess.DoesNotExist:
                    tier = 0
                return AccessResult(
                    tier=tier,
                    identity=email,
                    is_trial=False,
                    uses_remaining=None,
                    client_label=email,
                    code=None,
                )
        # JWT present (valid or invalid) but unusable → no access, skip code path
        return AccessResult(0, None, False, None, None, None)

    # ------------------------------------------------------------------
    # Step 2: Access code path
    # ------------------------------------------------------------------
    raw_code = request.headers.get("X-Broadcast-Access-Code")
    if raw_code is None:
        data = getattr(request, "data", None)
        if isinstance(data, dict):
            raw_code = data.get("access_code")

    if raw_code and isinstance(raw_code, str):
        incoming_hash = hash_code(raw_code)
        now = timezone.now()

        matched = None
        for code in AccessCode.objects.filter(is_active=True):
            if hmac.compare_digest(code.code_hash, incoming_hash):
                matched = code

        if matched is not None:
            if matched.expires_at is not None and matched.expires_at < now:
                return AccessResult(0, None, False, None, None, None)

            used = matched.uses.count()
            if matched.max_uses is not None:
                uses_remaining = max(matched.max_uses - used, 0)
                if used >= matched.max_uses:
                    already_counted = (
                        draft_id is not None and matched.uses.filter(draft_id=draft_id).exists()
                    )
                    if not already_counted:
                        return AccessResult(0, None, False, None, None, None)
            else:
                uses_remaining = None

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
