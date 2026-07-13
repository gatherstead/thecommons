"""Generate a hashed access code and print the raw code exactly once.

Two kinds of code:
  --kind trial   (default) Anonymous, always tier 2, time-boxed. Defaults to
                 unlimited uses + a 3-day expiry unless overridden.
  --kind upgrade Requires login to redeem (POST /broadcast/redeem);
                 permanently sets the account's tier. Defaults to 3 uses,
                 no expiry, unless overridden.

Usage:
    python manage.py generate_access_code --label "demo-booth"
    python manage.py generate_access_code --kind trial --trial-days 7 --unlimited
    python manage.py generate_access_code --kind upgrade --tier 2 --uses 1 --label "acme-co"
"""

import secrets
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from broadcast.access import hash_code
from broadcast.models import AccessCode


class Command(BaseCommand):
    help = "Generate a new access code (prints raw code once; only the hash is stored)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            type=str,
            choices=[AccessCode.KIND_TRIAL, AccessCode.KIND_UPGRADE],
            default=AccessCode.KIND_TRIAL,
            help="trial = anonymous/tier-2/time-boxed, "
            "upgrade = login-required/permanent (default: trial).",
        )
        parser.add_argument(
            "--tier",
            type=int,
            choices=[0, 1, 2],
            default=None,
            help="Tier granted — upgrade codes only. Trial codes are always tier 2.",
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
        parser.add_argument(
            "--trial-days",
            type=int,
            default=None,
            metavar="N",
            help="Expire N days from now — convenience alternative to --expires.",
        )

        uses_group = parser.add_mutually_exclusive_group()
        uses_group.add_argument(
            "--uses",
            type=int,
            default=None,
            metavar="N",
            help="Maximum number of uses. Mutually exclusive with --unlimited.",
        )
        uses_group.add_argument(
            "--unlimited",
            action="store_true",
            default=False,
            help="Allow unlimited uses. Mutually exclusive with --uses.",
        )

    def handle(self, *args, **options):  # noqa: C901  # linear option-resolution; complexity is inherent
        # call_command() doesn't run keyword-passed option values through
        # argparse's `type=`, so normalize here rather than trusting the
        # caller (real CLI usage is already int; tests calling via kwargs
        # otherwise pass raw strings straight through to int-typed logic).
        kind = options["kind"]
        tier_opt = int(options["tier"]) if options["tier"] is not None else None
        uses_opt = int(options["uses"]) if options["uses"] is not None else None
        trial_days_opt = int(options["trial_days"]) if options["trial_days"] is not None else None

        if options["expires"] and trial_days_opt is not None:
            raise CommandError("--expires and --trial-days are mutually exclusive.")

        # Resolve tier
        if kind == AccessCode.KIND_TRIAL:
            if tier_opt not in (None, 2):
                raise CommandError("Trial codes are always tier 2 — omit --tier.")
            tier = 2
        else:
            tier = tier_opt if tier_opt is not None else 2

        # Resolve max_uses — trial codes default to unlimited (time-boxed instead).
        if options["unlimited"]:
            max_uses = None
        elif uses_opt is not None:
            max_uses = uses_opt
        elif kind == AccessCode.KIND_TRIAL:
            max_uses = None
        else:
            max_uses = 3

        # Resolve expiry — trial codes default to a 3-day window.
        expires_at = None
        if trial_days_opt is not None:
            if trial_days_opt <= 0:
                raise CommandError("--trial-days must be a positive integer.")
            expires_at = timezone.now() + timedelta(days=trial_days_opt)
        elif options["expires"]:
            try:
                expires_at = datetime.fromisoformat(options["expires"])
            except ValueError as exc:
                raise CommandError(
                    f"Invalid --expires value '{options['expires']}'. "
                    "Use ISO 8601 format, e.g. 2026-12-31T23:59:59."
                ) from exc
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at)
        elif kind == AccessCode.KIND_TRIAL:
            expires_at = timezone.now() + timedelta(days=3)

        raw = secrets.token_urlsafe(24)
        code_hash = hash_code(raw)
        label = options["label"]

        AccessCode.objects.create(
            code_hash=code_hash,
            label=label,
            kind=kind,
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
        self.stdout.write(f"  kind  : {kind}")
        self.stdout.write(f"  tier  : {tier}")
        uses_display = "∞" if max_uses is None else str(max_uses)
        self.stdout.write(f"  uses  : {uses_display}")
        expiry_display = expires_at.isoformat() if expires_at else "—"
        self.stdout.write(f"  expiry: {expiry_display}")
        self.stdout.write(f"  hash  : {code_hash[:8]}...")
