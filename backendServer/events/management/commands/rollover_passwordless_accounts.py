"""Suite 38.A4 — roll over accounts stranded by the removed passwordless flow.

Before suite 38 (38.A1/38.A2), users could sign up/sign in with just an email
(no password) — a `neon_auth.user` row existed but with no matching
`neon_auth.account` row for `provider_id='credential'`, or a credential row
with a null password. Now that the passwordless flow is gone (SignInForm.tsx
requires email + password), those users are locked out: there is no
password for them to enter.

This command identifies those users and, with --send, emails each one a
rollover notice via Brevo (events.email_service.send_email). Defaults to a
dry run: it only prints who would be emailed.

IMPORTANT — read docs/suite-38-passwordless-rollover.md before ever passing
--send. As of 2026-07-31 the link this email points users to does NOT yet
lead anywhere functional: Better Auth's reset-password endpoint is disabled
(`emailAndPassword.sendResetPassword` is unset in theCommonsWeb/src/lib/auth.ts),
there is no `/reset-password/[token]` page, and the existing `/forgot-password`
page is a stale stub left over from the passwordless era (it tells users "we
don't send reset emails, just sign in without a password" — which is no
longer true and doesn't call any Better Auth API). Sending this email before
that wiring lands would hand users a dead-end link. See the doc for the
exact prerequisite changes and how to verify them before an actual --send.
"""

import os

from django.core.management.base import BaseCommand
from django.db import connection

from events.email_service import send_email

# Where the "set your password" call to action points. This is the frontend
# self-serve entry point named in the 38.A4 decision. As documented above and
# in docs/suite-38-passwordless-rollover.md, this page must be rewired to
# actually call Better Auth's requestPasswordReset before this link works —
# do not --send until that prerequisite is done and verified.
RESET_PATH = "/forgot-password"

EMAIL_SUBJECT = "Action needed: set a password for your Commons account"


def _reset_url() -> str:
    site_url = os.environ.get("SITE_URL", "https://www.thecommons.town")
    return f"{site_url}{RESET_PATH}"


def _email_html(name: str) -> str:
    reset_url = _reset_url()
    return (
        f"<p>Hi {name},</p>"
        "<p>We've changed how sign-in works on The Commons. Your account was created "
        'before we required a password, so the old "just enter your email" sign-in '
        "no longer works for you.</p>"
        f'<p><a href="{reset_url}">Set your password</a> to keep using your account — '
        "it only takes a minute.</p>"
        "<p>If you don't recognize this account, you can safely ignore this email.</p>"
        "<p>— The Commons</p>"
    )


def _email_text(name: str) -> str:
    reset_url = _reset_url()
    return (
        f"Hi {name},\n\n"
        "We've changed how sign-in works on The Commons. Your account was created "
        'before we required a password, so the old "just enter your email" sign-in '
        "no longer works for you.\n\n"
        f"Set your password here: {reset_url}\n\n"
        "If you don't recognize this account, you can safely ignore this email.\n\n"
        "— The Commons"
    )


def find_affected_users() -> list[dict]:
    """Return neon_auth users with no usable credential-provider password.

    Raw SQL, not the ORM, and for a more concrete reason than "it's a mirror
    table": BetterAuthAccount.user_id (events/models.py) is declared as a
    Django TextField, but the live `neon_auth.account."userId"` column is
    actually `uuid` (confirmed via information_schema.columns against the
    test DB — the model's type annotation has drifted from the schema it
    mirrors). An ORM anti-join such as

        BetterAuthUser.objects.exclude(
            id__in=BetterAuthAccount.objects.filter(
                provider_id="credential", password__isnull=False,
            ).values("user_id")
        )

    asks Django to bind the subquery's "userId" values as text (per the
    model field) against `u.id` (uuid), and Postgres has no `uuid = text`
    operator for a subquery comparison — it raises
    `operator does not exist: uuid = text` at query time (reproduced while
    building this command). Raw SQL sidesteps the model's stale type
    entirely: both columns really are `uuid`, so a plain LEFT JOIN with no
    cast is correct. Both mirror tables are managed=False; this is a
    read-only SELECT, never a migration.
    """
    query = """
        SELECT u.id, u.email, u.name
        FROM neon_auth."user" u
        LEFT JOIN neon_auth."account" a
          ON a."userId" = u.id
         AND a."providerId" = 'credential'
         AND a.password IS NOT NULL
        WHERE a.id IS NULL
        ORDER BY u.email
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    return [{"id": row[0], "email": row[1], "name": row[2]} for row in rows]


class Command(BaseCommand):
    help = (
        "Suite 38.A4: find neon_auth users left stranded by the removed "
        "passwordless flow (no credential-provider account with a non-null "
        "password) and, with --send, email each a rollover notice via Brevo. "
        "Defaults to a dry run that only lists affected users — sends nothing. "
        "Read docs/suite-38-passwordless-rollover.md before ever passing --send."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--send",
            action="store_true",
            help="Actually send the rollover email via Brevo. Omit for a dry "
            "run (default): prints the affected users and sends nothing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only process the first N affected users — useful for a "
            "small canary batch before sending to everyone.",
        )

    def handle(self, *args, **options):
        send = options["send"]
        limit = options["limit"]

        affected = find_affected_users()
        if limit is not None:
            affected = affected[:limit]

        self.stdout.write(
            f"Found {len(affected)} account(s) with no usable password "
            f"(neon_auth.user with no credential/password neon_auth.account row)."
        )
        for row in affected:
            self.stdout.write(f"  - {row['email']}  ({row['id']})")

        if not send:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run only — no emails sent. Re-run with --send to actually "
                    "email these users (see docs/suite-38-passwordless-rollover.md "
                    "for the prerequisite wiring to check first)."
                )
            )
            return

        if not affected:
            self.stdout.write("Nothing to send.")
            return

        sent, failed = 0, 0
        for row in affected:
            display_name = row["name"] or row["email"]
            ok = send_email(
                to=row["email"],
                subject=EMAIL_SUBJECT,
                html=_email_html(display_name),
                text=_email_text(display_name),
            )
            if ok:
                sent += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Sent: {sent}, Failed: {failed}"))
