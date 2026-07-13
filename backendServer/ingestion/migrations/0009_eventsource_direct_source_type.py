from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0007_seed_ingest_beat"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eventsource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("ics", "ICS/iCal Feed"),
                    ("scraper", "Web Scraper"),
                    ("email", "Email Inbox"),
                    ("direct", "Direct Host Submission"),
                ],
                max_length=20,
            ),
        ),
    ]
