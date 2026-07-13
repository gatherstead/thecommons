"""Grant or update a user's broadcast tier by email.

Usage:
    python manage.py set_broadcast_access aryav@unc.edu 2
"""

from django.core.management.base import BaseCommand

from broadcast.models import BroadcastAccess


class Command(BaseCommand):
    help = "Grant or update a user's broadcast tier by email."

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="User email address.")
        parser.add_argument(
            "tier",
            type=int,
            choices=[0, 1, 2],
            help="Access tier (0=none, 1=basic, 2=full).",
        )

    def handle(self, *args, **options):
        email = options["email"].lower()
        new_tier = options["tier"]

        obj, created = BroadcastAccess.objects.get_or_create(
            email=email,
            defaults={"tier": new_tier},
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"{email}: tier none → {new_tier}"))
        else:
            old_tier = obj.tier
            obj.tier = new_tier
            obj.save()
            self.stdout.write(self.style.SUCCESS(f"{email}: tier {old_tier} → {new_tier}"))
