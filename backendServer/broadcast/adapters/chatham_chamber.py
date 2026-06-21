from broadcast.adapters._generic import FieldSpec, standard_fill_and_submit
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import Eligibility

_CAT_MAP = {
    "music": "Entertainment", "arts": "Arts & Culture", "family-kids": "Family",
    "food-drink": "Food & Drink", "festival": "Festivals", "market": "Shopping",
    "literary": "Arts & Culture", "community": "Community", "nightlife": "Entertainment",
    "wellness": "Health & Wellness", "education": "Education",
}

_FIELDS = {
    "title": FieldSpec("Event Title", required=True),
    "description": FieldSpec("Description", required=True),
    "start_date": FieldSpec("Start Date", required=True),
    "start_time": FieldSpec("Start Time"),
    "end_date": FieldSpec("End Date"),
    "end_time": FieldSpec("End Time"),
    "venue_name": FieldSpec("Location", required=True),
    "address": FieldSpec("Address"),
    "event_url": FieldSpec("Website"),
    "price": FieldSpec("Admission"),
    "contact_email": FieldSpec("Email"),
    "contact_phone": FieldSpec("Phone"),
}


class ChathamChamberAdapter(SiteAdapter):
    key = "chatham_chamber"
    name = "Chatham Chamber Events"
    # ChamberMaster submission page; may be member-gated — a login wall at
    # runtime yields needs_manual, never a bypass.
    #IDK about this one chief
    submission_url = "https://business.ccucc.net/ap/Event/Submit/yr4lawrl"
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
