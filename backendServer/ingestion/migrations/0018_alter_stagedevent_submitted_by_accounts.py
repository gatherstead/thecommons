# StagedEvent.submitted_by now targets accounts.BetterAuthUser (moved out of
# events/ — see accounts/migrations/0001_initial.py and
# events/migrations/0021_move_identity_to_accounts.py). state_operations only
# — no DDL runs; db_constraint=False means there was never a DB-level FK.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0017_rawevent_raw_organizer"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="stagedevent",
                    name="submitted_by",
                    field=models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="submitted_staged_events",
                        to="accounts.betterauthuser",
                    ),
                ),
            ],
        ),
    ]
