from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Completely erase a user account by email (neon_auth + all Django-side data)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            required=True,
            help='Email address of the account to delete.',
        )

    def handle(self, *args, **options):
        from events.models import BetterAuthUser, NewsletterSubscriber, UserProfile, BusinessProfile

        email = options['email'].strip().lower()

        # --- Django-side rows (no real FK constraints, so delete manually) ---
        try:
            ba_user = BetterAuthUser.objects.get(email__iexact=email)
            user_id = ba_user.id
        except BetterAuthUser.DoesNotExist:
            user_id = None

        deleted_profile = UserProfile.objects.filter(user_id=user_id).delete()[0] if user_id else 0
        deleted_biz = BusinessProfile.objects.filter(user_id=user_id).delete()[0] if user_id else 0
        deleted_newsletter = NewsletterSubscriber.objects.filter(email__iexact=email).delete()[0]

        # --- neon_auth schema (raw SQL — Django won't generate DDL for managed=False tables) ---
        # Cascade on neon_auth.user wipes session, account, and verification rows automatically.
        if user_id is None:
            self.stdout.write(self.style.WARNING(
                f"No neon_auth.user found for {email}. "
                f"Cleaned up newsletter subscriber if present."
            ))
            self.stdout.write(f"  newsletter rows deleted : {deleted_newsletter}")
            return

        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM "neon_auth"."user" WHERE id = %s', [str(user_id)])
            neon_rows = cursor.rowcount

        self.stdout.write(self.style.SUCCESS(f"Deleted account: {email}"))
        self.stdout.write(f"  neon_auth.user (+ cascaded session/account/verification) : {neon_rows}")
        self.stdout.write(f"  UserProfile rows deleted    : {deleted_profile}")
        self.stdout.write(f"  BusinessProfile rows deleted: {deleted_biz}")
        self.stdout.write(f"  NewsletterSubscriber rows   : {deleted_newsletter}")
