from rest_framework.permissions import BasePermission

from broadcast.access import resolve_client_label


class HasBroadcastAccessCode(BasePermission):
    """Validates the broadcast access code from the request body.

    On success, stamps the resolved client label onto the request as
    `request.broadcast_client_label`. Standalone — does not use anything
    from backend/permissions.py (isolation contract).
    """

    message = "Invalid or missing access code."

    def has_permission(self, request, view):
        code = request.headers.get("X-Broadcast-Access-Code")
        if not code and isinstance(request.data, dict):
            code = request.data.get("access_code")
        label = resolve_client_label(code)
        if label is None:
            return False
        request.broadcast_client_label = label
        return True
