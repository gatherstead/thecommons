from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0004_add_safety_score_to_stagedevent"),
        ("events", "0007_event_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="stagedevent",
            name="submitted_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="submitted_staged_events",
                to="events.betterauthuser",
            ),
        ),
    ]
