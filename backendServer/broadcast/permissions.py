"""Broadcast-specific permission classes.

Standalone — imports only from broadcast/ and rest_framework.
Does NOT import from backend/permissions.py (isolation contract).
"""

from rest_framework.permissions import BasePermission

from broadcast.access import authenticated_email, resolve_access


def _draft_id_from(request):
    """Extract draft_id from the request body, handling nested event dicts."""
    data = getattr(request, "data", None)
    if isinstance(data, dict):
        draft_id = data.get("draft_id")
        if draft_id is not None:
            return draft_id
        event = data.get("event")
        if isinstance(event, dict):
            return event.get("draft_id")
    return None


class _BroadcastTierPermission(BasePermission):
    """Gate on a minimum broadcast access tier.

    Stamps request.broadcast_access (AccessResult) and
    request.broadcast_client_label for downstream views.
    """

    min_tier = 0
    message = "No broadcast access — log in or enter an access code."

    def has_permission(self, request, view):
        draft_id = _draft_id_from(request)
        result = resolve_access(request, draft_id=draft_id)
        request.broadcast_access = result
        request.broadcast_client_label = result.client_label
        return result.tier >= self.min_tier


class RequiresBroadcastTier1(_BroadcastTierPermission):
    """Allow tier 1+ (standard broadcast access)."""

    min_tier = 1


class RequiresBroadcastTier2(_BroadcastTierPermission):
    """Allow tier 2+ (AI features require elevated access)."""

    min_tier = 2


class RequiresBroadcastLogin(BasePermission):
    """Require a valid Better Auth JWT — no tier check.

    Stamps request.broadcast_email for use by upgrade-code redemption, which
    is deliberately unavailable to anonymous/access-code sessions.
    """

    message = "Log in to upgrade your account."

    def has_permission(self, request, view):
        email = authenticated_email(request)
        if email is None:
            return False
        request.broadcast_email = email
        return True
