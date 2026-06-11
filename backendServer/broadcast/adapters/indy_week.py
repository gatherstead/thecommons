from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import TRIANGLE, Eligibility

_CAT_MAP = {
    "music": "Music", "arts": "Arts", "family-kids": "Kids & Family",
    "food-drink": "Food & Drink", "festival": "Festivals", "market": "Markets",
    "literary": "Literary", "community": "Community", "nightlife": "Nightlife",
    "wellness": "Health & Wellness", "education": "Classes",
}

_FIELDS = {
    "title": FieldSpec("Event Name", required=True),
    "description": FieldSpec("Description", required=True),
    "start_date": FieldSpec("Start Date", required=True),
    "start_time": FieldSpec("Start Time"),
    "end_date": FieldSpec("End Date"),
    "venue_name": FieldSpec("Venue", required=True),
    "address": FieldSpec("Address"),
    "event_url": FieldSpec("Website"),
    "ticket_url": FieldSpec("Ticket Link"),
    "price": FieldSpec("Price"),
    "contact_email": FieldSpec("Email"),
}


class IndyWeekAdapter(SiteAdapter):
    key = "indy_week"
    name = "INDY Week"
    # The calendar is an embedded SPA; if it demands an account at runtime the
    # flow returns needs_manual (login walls are never bypassed).
    submission_url = "https://indyweek.com/calendar/#/"
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
