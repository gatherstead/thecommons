from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import TRIANGLE, Eligibility

# Static category mapping — deterministic per-site config, never generated.
_CAT_MAP = {
    "music": "Music", "arts": "Arts & Culture", "family-kids": "Family",
    "food-drink": "Food & Drink", "festival": "Festivals", "market": "Markets",
    "literary": "Arts & Culture", "community": "Community", "nightlife": "Nightlife",
    "wellness": "Health & Wellness", "education": "Classes & Workshops",
}

# Best-guess labels — replace with captured selectors via scaffold_adapter
# before enabling real (non-dry-run) submissions.
_FIELDS = {
    "title": FieldSpec("Event Title", required=True),
    "description": FieldSpec("Description", required=True),
    "start_date": FieldSpec("Start Date", required=True),
    "start_time": FieldSpec("Start Time"),
    "end_date": FieldSpec("End Date"),
    "venue_name": FieldSpec("Venue Name", required=True),
    "address": FieldSpec("Address"),
    "event_url": FieldSpec("Event Website"),
    "price": FieldSpec("Cost"),
}


class TriangleOnTheCheapAdapter(SiteAdapter):
    key = "triangle_on_the_cheap"
    name = "Triangle on the Cheap"
    submission_url = "https://triangleonthecheap.com/submit-an-event/"
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())

    def fill_and_submit(self, page, ev, ctx):
        return standard_fill_and_submit(
            self, page, ev, ctx,
            fields=_FIELDS,
            cat_map=_CAT_MAP,
            categories_label="Category",
            image_label="Event Image",
            submit_button="Submit Event",
        )
