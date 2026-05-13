from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission


class BearerTokenAuthentication(BaseAuthentication):
    """
    Accepts `Authorization: Bearer <value>` where <value> is either a
    Better Auth–issued JWT (verified statelessly against the JWKS endpoint
    exposed by Next.js) or the shared THE_COMMONS_API_KEY.

    For the API-key path, no user is attached (returns None) so anonymous-
    but-authorized callers are still allowed by permission classes that
    accept the shared key.
    """

    def authenticate(self, request):
        auth = request.META.get('HTTP_AUTHORIZATION', '').split()
        if len(auth) != 2 or auth[0].lower() != 'bearer':
            return None

        token_value = auth[1]
        if settings.THE_COMMONS_API_KEY and token_value == settings.THE_COMMONS_API_KEY:
            return None

        from backend.jwt_auth import verify_better_auth_jwt
        from events.models import BetterAuthUser

        claims = verify_better_auth_jwt(token_value)
        if claims is None:
            raise AuthenticationFailed('Invalid token')

        user_id = claims.get('sub')
        if not user_id:
            raise AuthenticationFailed('Token missing subject')

        try:
            user = BetterAuthUser.objects.get(id=user_id)
        except BetterAuthUser.DoesNotExist:
            raise AuthenticationFailed('Unknown user')

        return (user, claims)

    def authenticate_header(self, request):
        return 'Bearer'


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


class HasCommonsAPIKeyOrUser(BasePermission):
    """
    Allow either an authenticated user (via BearerTokenAuthentication) or a
    request bearing the shared THE_COMMONS_API_KEY.
    """
    message = 'Authentication required.'

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        auth = request.headers.get('Authorization', '')
        return bool(settings.THE_COMMONS_API_KEY) and auth == f"Bearer {settings.THE_COMMONS_API_KEY}"
