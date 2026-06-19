"""Auth-bridge tests that drive the real BearerTokenAuthentication →
verify_better_auth_jwt path, stubbing only at the JWKS HTTP boundary.

A deep patch on `authenticate`/`verify_better_auth_jwt` could go green while the
real JWKS decode path is broken, so we sign a genuine RS256 token and intercept
only the network fetch of the signing key.
"""
import contextlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings, tag
from django.urls import reverse

import backend.jwt_auth as jwt_auth
from events.models import BetterAuthAccount

from .factories import make_user


@tag('db')
@override_settings(
    BETTER_AUTH_JWKS_URL='https://stub.invalid/jwks',
    BETTER_AUTH_ISSUER='',
    BETTER_AUTH_AUDIENCE='',
)
class AuthBridgeTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()

    def setUp(self):
        # The bridge caches a PyJWKClient in-process for 600s; reset so each test
        # starts from a clean fetch.
        jwt_auth._jwks_cache.update({'client': None, 'fetched_at': 0.0, 'stale_after': 0.0})
        self.user = make_user('LOCAL')

    def _token_for(self, sub):
        return jwt.encode(
            {'sub': str(sub), 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            self.private_key,
            algorithm='RS256',
        )

    @contextlib.contextmanager
    def _stub_jwks(self):
        signing = SimpleNamespace(key=self.public_key)
        with mock.patch('backend.jwt_auth.requests.get') as rget, mock.patch(
            'backend.jwt_auth.PyJWKClient.get_signing_key_from_jwt', return_value=signing
        ):
            rget.return_value.raise_for_status.return_value = None
            yield

    def _add_credential(self, user):
        now = datetime.now(timezone.utc)
        BetterAuthAccount.objects.create(
            id=uuid.uuid4().hex,
            account_id=uuid.uuid4().hex,
            provider_id='credential',
            user_id=str(user.id),
            password='hashed-secret',
            created_at=now,
            updated_at=now,
        )

    def test_valid_jwt_authenticates_and_returns_profile(self):
        token = self._token_for(self.user.id)
        with self._stub_jwks():
            resp = self.client.get(reverse('auth-me'), HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['email'], self.user.email)

    def test_has_password_true_with_credential_account(self):
        self._add_credential(self.user)
        token = self._token_for(self.user.id)
        with self._stub_jwks():
            resp = self.client.get(reverse('auth-me'), HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['has_password'])

    def test_has_password_false_without_credential_account(self):
        token = self._token_for(self.user.id)
        with self._stub_jwks():
            resp = self.client.get(reverse('auth-me'), HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['has_password'])

    def test_patch_me_updates_through_bridge(self):
        token = self._token_for(self.user.id)
        with self._stub_jwks():
            resp = self.client.patch(
                reverse('auth-me'),
                data={'primary_city': 'carrboro'},
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {token}',
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['primary_city'], 'carrboro')

    def test_unknown_subject_is_rejected(self):
        token = self._token_for(uuid.uuid4())
        with self._stub_jwks():
            resp = self.client.get(reverse('auth-me'), HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(resp.status_code, 401)

    def test_garbage_token_is_rejected(self):
        with self._stub_jwks():
            resp = self.client.get(reverse('auth-me'), HTTP_AUTHORIZATION='Bearer not-a-jwt')
        self.assertEqual(resp.status_code, 401)

    @override_settings(THE_COMMONS_API_KEY='shared-key')
    def test_api_key_attaches_no_user_so_me_is_401(self):
        # The API-key path authorizes anonymous callers (no user attached), so an
        # endpoint requiring an authenticated user must still reject it.
        resp = self.client.get(reverse('auth-me'), HTTP_AUTHORIZATION='Bearer shared-key')
        self.assertEqual(resp.status_code, 401)
