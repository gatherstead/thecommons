from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0007_event_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="is_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="event",
            name="source_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
