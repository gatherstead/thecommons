from django.db import migrations, models
import django.db.models.deletion


INITIAL_TOWNS = [
    {'slug': 'carrboro', 'name': 'Carrboro'},
    {'slug': 'pittsboro', 'name': 'Pittsboro'},
]


def seed_towns(apps, schema_editor):
    Town = apps.get_model('events', 'Town')
    for town in INITIAL_TOWNS:
        Town.objects.get_or_create(slug=town['slug'], defaults={'name': town['name']})


def migrate_town_strings_to_fk(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    Town = apps.get_model('events', 'Town')
    for event in Event.objects.all():
        if event.town_str:
            town = Town.objects.filter(slug=event.town_str).first()
            if town:
                event.town_new = town
                event.save()


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0003_event_link'),
    ]

    operations = [
        # 1. Create the Town table
        migrations.CreateModel(
            name='Town',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=100)),
            ],
        ),

        # 2. Seed initial towns
        migrations.RunPython(seed_towns, migrations.RunPython.noop),

        # 3. Rename old CharField so we can add a FK named 'town' later
        migrations.RenameField(
            model_name='event',
            old_name='town',
            new_name='town_str',
        ),

        # 4. Add the new nullable FK with a temp name
        migrations.AddField(
            model_name='event',
            name='town_new',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='events',
                to='events.town',
            ),
        ),

        # 5. Convert existing string values to FK references
        migrations.RunPython(migrate_town_strings_to_fk, migrations.RunPython.noop),

        # 6. Drop the old CharField
        migrations.RemoveField(
            model_name='event',
            name='town_str',
        ),

        # 7. Rename town_new → town
        migrations.RenameField(
            model_name='event',
            old_name='town_new',
            new_name='town',
        ),
    ]
