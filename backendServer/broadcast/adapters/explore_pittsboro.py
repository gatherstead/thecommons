from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import Eligibility

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
    "venue_name": FieldSpec("Venue", required=True),
    "address": FieldSpec("Address"),
    "event_url": FieldSpec("Website"),
    "price": FieldSpec("Price"),
    "contact_email": FieldSpec("Email"),
}


class ExplorePittsboroAdapter(SiteAdapter):
    key = "explore_pittsboro"
    name = "Explore Pittsboro"
    #I dont know aobut this on
    submission_url = "https://www.explorepittsboro.com/events"
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"pittsboro", "chatham"}), categories=frozenset()
    )

    def fill_and_submit(self, page, ev, ctx):
        return standard_fill_and_submit(
            self, page, ev, ctx,
            fields=_FIELDS,
            cat_map=_CAT_MAP,
            categories_label="Category",
            image_label="Image",
            submit_button="Submit",
        )
