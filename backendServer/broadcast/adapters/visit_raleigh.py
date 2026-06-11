from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import Eligibility

_CAT_MAP = {
    "music": "Live Music", "arts": "Arts & Culture", "family-kids": "Family Friendly",
    "food-drink": "Food & Drink", "festival": "Festivals", "market": "Shopping",
    "literary": "Arts & Culture", "community": "Community", "nightlife": "Nightlife",
    "wellness": "Sports & Recreation", "education": "Classes & Workshops",
}

_FIELDS = {
    "title": FieldSpec("Event Name", required=True),
    "description": FieldSpec("Description", required=True),
    "start_date": FieldSpec("Start Date", required=True),
    "start_time": FieldSpec("Start Time"),
    "end_date": FieldSpec("End Date"),
    "end_time": FieldSpec("End Time"),
    "venue_name": FieldSpec("Venue Name", required=True),
    "address_line1": FieldSpec("Address"),
    "city": FieldSpec("City"),
    "zip": FieldSpec("Zip"),
    "event_url": FieldSpec("Event Website"),
    "ticket_url": FieldSpec("Ticket URL"),
    "price": FieldSpec("Admission"),
    "contact_email": FieldSpec("Email"),
    "contact_phone": FieldSpec("Phone"),
}


class VisitRaleighAdapter(SiteAdapter):
    key = "visit_raleigh"
    name = "Visit Raleigh"
    submission_url = "https://www.visitraleigh.com/events/submit-an-event/"
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"raleigh", "wake", "cary"}), categories=frozenset()
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
