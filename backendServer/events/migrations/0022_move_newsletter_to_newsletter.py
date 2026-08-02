# NewsletterSubscriber moved to newsletter/ (see
# newsletter/migrations/0001_initial.py for the paired create).
# state_operations only — no DDL runs; the physical table
# (events_newslettersubscriber) is untouched.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0021_move_identity_to_accounts"),
        ("newsletter", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="NewsletterSubscriber"),
            ],
        ),
    ]
