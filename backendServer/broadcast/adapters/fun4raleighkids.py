from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import Eligibility

_CAT_MAP = {"family-kids": "Family Events"}

_FIELDS = {
    "title": FieldSpec("Event Title", required=True),
    "description": FieldSpec("Description", required=True),
    "start_date": FieldSpec("Start Date", required=True),
    "start_time": FieldSpec("Start Time"),
    "end_date": FieldSpec("End Date"),
    "venue_name": FieldSpec("Venue", required=True),
    "address": FieldSpec("Address"),
    "event_url": FieldSpec("Website"),
    "price": FieldSpec("Cost"),
    "contact_email": FieldSpec("Email"),
}


class Fun4RaleighKidsAdapter(SiteAdapter):
    key = "fun4raleighkids"
    name = "Fun 4 Raleigh Kids"
    submission_url = "https://fun4raleighkids.com/calendar/"
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"raleigh", "wake", "cary", "triangle"}),
        categories=frozenset({"family-kids"}),
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
