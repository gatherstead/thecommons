"""Suite 50: retire event categories entirely.

Owner decision (2026-08-05, reaffirming the 2026-08-04 answer to the original
49.11 ticket): categories go away in favour of the suite-47 tag vocabulary.

⚠️ ONE-WAY. Dropping the M2M table destroys every event↔category link, and
DeleteModel drops the 9 seeded rows. `reverse_code` cannot bring the links back
— re-applying the model would give empty categories. The deploy takes an
automatic pre-migrate `pg_dump`, which is the only recovery path.

Note this removes a genuine dimension rather than migrating it: the tag
vocabulary is orthogonal (day-part/price/accessibility), so there is no tag for
"music". Genre filtering is gone, not relocated.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0025_delete_retired_tags"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="event",
            name="categories",
        ),
        migrations.DeleteModel(
            name="Category",
        ),
    ]
