from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import TRIANGLE, Eligibility

_CAT_MAP = {
    "music": "Music", "arts": "Arts", "family-kids": "Family",
    "food-drink": "Food & Drink", "festival": "Festival", "market": "Market",
    "literary": "Arts", "community": "Community", "nightlife": "Nightlife",
    "wellness": "Wellness", "education": "Education",
}

_FIELDS = {
    "title": FieldSpec("Event Title", required=True),
    "description": FieldSpec("Description", required=True),
    "start_date": FieldSpec("Start Date", required=True),
    "start_time": FieldSpec("Start Time"),
    "end_date": FieldSpec("End Date"),
    "end_time": FieldSpec("End Time"),
    "venue_name": FieldSpec("Venue", required=True),
    "address": FieldSpec("Address"),
    "event_url": FieldSpec("Website"),
    "ticket_url": FieldSpec("Tickets"),
    "price": FieldSpec("Cost"),
    "organizer_name": FieldSpec("Organizer"),
    "contact_email": FieldSpec("Email"),
    "contact_phone": FieldSpec("Phone"),
}


class TriangleWeekenderAdapter(SiteAdapter):
    key = "triangle_weekender"
    name = "The Triangle Weekender"
    submission_url = "https://thetriangleweekender.com/events/community/add/"
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())

    def fill_and_submit(self, page, ev, ctx):
        return standard_fill_and_submit(
            self, page, ev, ctx,
            fields=_FIELDS,
            cat_map=_CAT_MAP,
            categories_label="Category",
            image_label="Image",
            submit_button="Submit",
        )
