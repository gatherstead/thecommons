from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import Eligibility

_CAT_MAP = {"arts": "Arts", "literary": "Literary"}

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


class ChathamArtsAdapter(SiteAdapter):
    key = "chatham_arts"
    name = "Chatham Arts Council"
    submission_url = "https://www.chathamartscouncil.org/calendar/"
    requires_auth = False
    # arts/literary only — "don't submit a non-art event to an arts calendar"
    eligibility = Eligibility(
        localities=frozenset({"pittsboro", "chatham"}),
        categories=frozenset({"arts", "literary"}),
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
