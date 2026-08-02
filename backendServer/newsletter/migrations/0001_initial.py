# NewsletterSubscriber now lives in newsletter/ (see events/migrations/
# 0022_move_newsletter_to_newsletter.py for the paired events-side move).
# state_operations only — no DDL runs; the physical table
# (events_newslettersubscriber) is untouched.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("events", "0021_move_identity_to_accounts"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="NewsletterSubscriber",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("email", models.EmailField(max_length=254, unique=True)),
                        (
                            "frequency",
                            models.CharField(
                                choices=[("WEEKLY", "Weekly"), ("MONTHLY", "Monthly")],
                                default="WEEKLY",
                                max_length=10,
                            ),
                        ),
                        ("is_active", models.BooleanField(default=True)),
                        ("subscribed_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "manage_token",
                            models.UUIDField(
                                default=uuid.uuid4, editable=False, unique=True, db_index=True
                            ),
                        ),
                    ],
                    options={
                        "db_table": "events_newslettersubscriber",
                    },
                ),
            ],
        ),
    ]
