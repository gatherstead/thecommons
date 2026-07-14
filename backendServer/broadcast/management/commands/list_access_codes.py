"""List all access codes in the database, including the raw code for lookup/copy.

Usage:
    python manage.py list_access_codes
"""

from django.core.management.base import BaseCommand

from broadcast.models import AccessCode


class Command(BaseCommand):
    help = "List all access codes (id, code, label, kind, tier, uses, active, expiry)."

    def handle(self, *args, **options):
        codes = AccessCode.objects.order_by("id")
        if not codes.exists():
            self.stdout.write("No access codes found.")
            return

        header = (
            f"{'ID':>5}  {'CODE':32}  {'LABEL':<24}  {'KIND':7}  {'TIER':4}  "
            f"{'USES':10}  {'ACTIVE':6}  EXPIRY"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        for code in codes:
            label = code.label if code.label else "(no label)"
            used = (
                code.uses.count()
                if code.kind == AccessCode.KIND_TRIAL
                else code.redemptions.count()
            )
            if code.max_uses is None:
                uses_str = f"{used}/∞"
            else:
                uses_str = f"{used}/{code.max_uses}"
            active_str = "yes" if code.is_active else "no"
            expiry_str = code.expires_at.isoformat() if code.expires_at else "—"
            code_display = code.code if code.code else f"(pre-existing, hash {code.code_hash[:8]})"

            self.stdout.write(
                f"{code.id:>5}  {code_display:32}  {label:<24}  {code.kind:<7}  {code.tier:>4}  "
                f"{uses_str:>10}  {active_str:>6}  {expiry_str}"
            )
