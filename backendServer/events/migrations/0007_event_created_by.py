from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0006_swap_user_to_betterauth"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="created_events",
                to="events.betterauthuser",
            ),
        ),
    ]
