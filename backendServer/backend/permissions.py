from django.conf import settings
from rest_framework.permissions import BasePermission


class HasCommonsAPIKey(BasePermission):
    """
    Requires the request to include the The Commons API key:
        Authorization: Bearer <THE_COMMONS_API_KEY>
    Apply to any endpoint that should only be callable through the app.
    """
    message = 'Invalid or missing API key.'

    def has_permission(self, request, view):
        auth = request.headers.get('Authorization', '')
        return auth == f"Bearer {settings.THE_COMMONS_API_KEY}"
