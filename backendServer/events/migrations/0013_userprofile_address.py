from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0012_add_category_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='address',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
