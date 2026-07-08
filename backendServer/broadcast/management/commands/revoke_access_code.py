"""Revoke an access code by label or numeric primary key.

Usage:
    python manage.py revoke_access_code "partner-x"
    python manage.py revoke_access_code 7
"""
from django.core.management.base import BaseCommand, CommandError

from broadcast.models import AccessCode


class Command(BaseCommand):
    help = "Revoke an access code by exact label or numeric id."

    def add_arguments(self, parser):
        parser.add_argument(
            "label_or_id",
            type=str,
            help="Exact label string or numeric primary key of the code to revoke.",
        )

    def handle(self, *args, **options):
        value = options["label_or_id"]

        # Try numeric pk first.
        code = None
        if value.isdigit():
            try:
                code = AccessCode.objects.get(pk=int(value))
            except AccessCode.DoesNotExist:
                raise CommandError(f"No access code with id={value}.")
        else:
            # Match by exact label.
            matches = AccessCode.objects.filter(label=value)
            if not matches.exists():
                raise CommandError(f"No access code with label '{value}'.")
            active_matches = matches.filter(is_active=True)
            if active_matches.count() > 1:
                lines = [
                    f"Multiple active codes share label '{value}'. "
                    "Revoke by id instead:"
                ]
                for m in active_matches.order_by("id"):
                    lines.append(
                        f"  id={m.id}  label='{m.label}'  "
                        f"created={m.created_at.date().isoformat()}"
                    )
                raise CommandError("\n".join(lines))
            if active_matches.exists():
                code = active_matches.first()
            else:
                # All matches are inactive; pick the first to give a useful message.
                code = matches.order_by("id").first()

        if not code.is_active:
            self.stdout.write(
                self.style.WARNING(
                    f"Code id={code.id} ('{code.label}') is already inactive — no change."
                )
            )
            return

        code.is_active = False
        code.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"Revoked code id={code.id} ('{code.label}', tier {code.tier})."
            )
        )
