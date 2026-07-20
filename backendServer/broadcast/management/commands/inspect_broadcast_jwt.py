"""Read-only diagnostic for a live Better-Auth JWT that fails verification in prod.

Decodes the token's header/payload without verifying the signature, prints the
Django-side Better Auth config, fetches the JWKS and lists its key ids, then
runs the real `verify_better_auth_jwt` to report PASS/FAIL. Never prints the
raw token, and performs no ORM access or writes.

Usage:
    python manage.py inspect_broadcast_jwt --token "eyJ..."
    echo "$TOKEN" | python manage.py inspect_broadcast_jwt
"""

import sys

import jwt
import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from backend.jwt_auth import verify_better_auth_jwt


class Command(BaseCommand):
    help = "Diagnose why a live Better-Auth JWT fails verification (read-only, no ORM writes)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            type=str,
            default=None,
            help="The JWT to inspect. If omitted, the token is read from stdin.",
        )

    def handle(self, *args, **options):
        token = options["token"] or sys.stdin.read().strip()
        if not token:
            self.stderr.write(
                self.style.ERROR("No token provided (use --token or pipe via stdin).")
            )
            return

        self.stdout.write(self.style.SUCCESS("=== Unverified header ==="))
        try:
            header = jwt.get_unverified_header(token)
            self.stdout.write(f"  alg: {header.get('alg')}")
            self.stdout.write(f"  kid: {header.get('kid')}")
        except jwt.PyJWTError as e:
            self.stdout.write(
                self.style.ERROR(f"  Could not decode header: {type(e).__name__}: {e}")
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Unverified payload ==="))
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            self.stdout.write(f"  iss: {payload.get('iss')}")
            self.stdout.write(f"  aud: {payload.get('aud')}")
            self.stdout.write(f"  email: {payload.get('email')}")
            self.stdout.write(f"  exp: {payload.get('exp')}")
        except jwt.PyJWTError as e:
            self.stdout.write(
                self.style.ERROR(f"  Could not decode payload: {type(e).__name__}: {e}")
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Django config ==="))
        jwks_url = getattr(settings, "BETTER_AUTH_JWKS_URL", "")
        issuer = getattr(settings, "BETTER_AUTH_ISSUER", "")
        audience = getattr(settings, "BETTER_AUTH_AUDIENCE", "")
        self.stdout.write(f"  BETTER_AUTH_JWKS_URL: {jwks_url or '(empty)'}")
        self.stdout.write(f"  BETTER_AUTH_ISSUER: {issuer or '(empty)'}")
        self.stdout.write(f"  BETTER_AUTH_AUDIENCE: {audience or '(empty)'}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== JWKS kids ==="))
        if not jwks_url:
            self.stdout.write(self.style.ERROR("  BETTER_AUTH_JWKS_URL is not configured."))
        else:
            try:
                resp = requests.get(jwks_url, timeout=5)
                resp.raise_for_status()
                keys = resp.json().get("keys", [])
                if not keys:
                    self.stdout.write(self.style.WARNING("  JWKS response contained no keys."))
                for key in keys:
                    kid = key.get("kid", "(no kid)")
                    alg = key.get("alg", "?")
                    kty = key.get("kty", "?")
                    self.stdout.write(f"  kid={kid} alg={alg} kty={kty}")
            except requests.RequestException as e:
                self.stdout.write(
                    self.style.ERROR(f"  Could not fetch JWKS: {type(e).__name__}: {e}")
                )
            except (ValueError, KeyError) as e:
                self.stdout.write(
                    self.style.ERROR(f"  Malformed JWKS response: {type(e).__name__}: {e}")
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Final verify (verify_better_auth_jwt) ==="))
        result = verify_better_auth_jwt(token)
        if result is None:
            self.stdout.write(self.style.ERROR("  FAIL: verify_better_auth_jwt returned None."))
            self.stdout.write(
                "  See WARNING-level logs from backend.jwt_auth for the underlying cause."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("  PASS: verify_better_auth_jwt returned a valid payload.")
            )
            self.stdout.write(f"  email: {result.get('email')}")
