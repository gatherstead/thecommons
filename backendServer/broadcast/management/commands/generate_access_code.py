"""Generate a hashed access code and print the raw code exactly once.

Usage:
    python manage.py generate_access_code --tier 2 --uses 5 --label "partner-x"
    python manage.py generate_access_code --unlimited --label "beta-tester"
    python manage.py generate_access_code --expires 2026-12-31T23:59:59
"""
import secrets
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from broadcast.access import hash_code
from broadcast.models import AccessCode


class Command(BaseCommand):
    help = "Generate a new access code (prints raw code once; only the hash is stored)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tier",
            type=int,
            choices=[0, 1, 2],
            default=2,
            help="Access tier granted by this code (default: 2).",
        )
        parser.add_argument(
            "--label",
            type=str,
            default="",
            help="Human-readable label for this code (default: empty).",
        )
        parser.add_argument(
            "--expires",
            type=str,
            default=None,
            metavar="ISO8601",
            help="Expiry datetime in ISO 8601 format, e.g. 2026-12-31T23:59:59.",
        )

        uses_group = parser.add_mutually_exclusive_group()
        uses_group.add_argument(
            "--uses",
            type=int,
            default=None,
            metavar="N",
            help="Maximum number of uses (default: 3). Mutually exclusive with --unlimited.",
        )
        uses_group.add_argument(
            "--unlimited",
            action="store_true",
            default=False,
            help="Allow unlimited uses. Mutually exclusive with --uses.",
        )

    def handle(self, *args, **options):
        # Resolve max_uses
        if options["unlimited"]:
            max_uses = None
        elif options["uses"] is not None:
            max_uses = options["uses"]
        else:
            max_uses = 3

        # Parse expiry
        expires_at = None
        if options["expires"]:
            try:
                expires_at = datetime.fromisoformat(options["expires"])
            except ValueError as exc:
                raise CommandError(
                    f"Invalid --expires value '{options['expires']}'. "
                    "Use ISO 8601 format, e.g. 2026-12-31T23:59:59."
                ) from exc
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at)

        raw = secrets.token_urlsafe(24)
        code_hash = hash_code(raw)
        label = options["label"]
        tier = options["tier"]

        AccessCode.objects.create(
            code_hash=code_hash,
            label=label,
            tier=tier,
            max_uses=max_uses,
            expires_at=expires_at,
        )

        # Print the raw code prominently — this is the only time it appears.
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("ACCESS CODE (copy now):"))
        self.stdout.write(self.style.SUCCESS(f"  {raw}"))
        self.stdout.write(self.style.WARNING("Store it now — it will not be shown again."))
        self.stdout.write("")
        self.stdout.write(f"  label : {label or '(none)'}")
        self.stdout.write(f"  tier  : {tier}")
        uses_display = "∞" if max_uses is None else str(max_uses)
        self.stdout.write(f"  uses  : {uses_display}")
        expiry_display = expires_at.isoformat() if expires_at else "—"
        self.stdout.write(f"  expiry: {expiry_display}")
        self.stdout.write(f"  hash  : {code_hash[:8]}...")
