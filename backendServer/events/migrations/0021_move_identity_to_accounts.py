# Identity/auth-bridge models (5 Better Auth mirrors + UserProfile +
# BusinessProfile) now live in accounts/ (see accounts/migrations/0001_initial.py).
# state_operations only — no DDL runs; the physical tables are untouched.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0020_seed_monthly_digest_beat"),
        ("accounts", "0001_initial"),
        # StagedEvent.submitted_by must be repointed off events.BetterAuthUser
        # (ingestion 0018) BEFORE we delete the model here, or the intervening
        # state has a dangling lazy FK reference. See orchestration notes.
        ("ingestion", "0018_alter_stagedevent_submitted_by_accounts"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="event",
                    name="created_by",
                    field=models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="created_events",
                        to="accounts.betterauthuser",
                    ),
                ),
                migrations.DeleteModel(name="BetterAuthUser"),
                migrations.DeleteModel(name="BetterAuthSession"),
                migrations.DeleteModel(name="BetterAuthAccount"),
                migrations.DeleteModel(name="BetterAuthVerification"),
                migrations.DeleteModel(name="BetterAuthJwks"),
                migrations.DeleteModel(name="UserProfile"),
                migrations.DeleteModel(name="BusinessProfile"),
            ],
        ),
    ]
