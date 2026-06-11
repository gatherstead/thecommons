from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import TRIANGLE, Eligibility

_CAT_MAP = {
    "music": "Music", "arts": "Arts", "family-kids": "Family",
    "food-drink": "Food", "festival": "Festivals", "market": "Shopping",
    "literary": "Arts", "community": "Community", "nightlife": "Entertainment",
    "wellness": "Health", "education": "Education",
}

_FIELDS = {
    "title": FieldSpec("Event Title", required=True),
    "description": FieldSpec("Event Description", required=True),
    "start_date": FieldSpec("Date", required=True),
    "start_time": FieldSpec("Time"),
    "venue_name": FieldSpec("Venue", required=True),
    "address": FieldSpec("Address"),
    "event_url": FieldSpec("Website"),
    "contact_email": FieldSpec("Email"),
    "contact_phone": FieldSpec("Phone"),
}


class Abc11CommunityAdapter(SiteAdapter):
    key = "abc11_community"
    name = "ABC11 Community Calendar"
    submission_url = "https://abc11.com/community/calendar/"
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())

    def fill_and_submit(self, page, ev, ctx):
        return standard_fill_and_submit(
            self, page, ev, ctx,
            fields=_FIELDS,
            cat_map=_CAT_MAP,
            categories_label="Category",
            submit_button="Submit",
        )
