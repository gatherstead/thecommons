"""Canonical event schema — the single shape adapters receive.

Decoupled from the ORM row so adapters never touch the database.
"""
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

# Target calendars are all in the NC Triangle. Submissions arrive as aware UTC
# (USE_TZ=True), so convert to Eastern before adapters format wall-clock times —
# otherwise a 4pm event is written as 8pm (its UTC equivalent).
EVENT_TZ = ZoneInfo("America/New_York")


def _to_local(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(EVENT_TZ)
    return dt


@dataclass
class CanonicalEvent:
    title: str
    description: str
    start_datetime: datetime
    venue_name: str
    address_line1: str
    zip: str
    locality: list[str]
    categories: list[str] = field(default_factory=list)
    city: str = ""
    end_datetime: datetime | None = None
    all_day: bool = False
    state: str = "NC"
    event_url: str = ""
    ticket_url: str = ""
    price: str = ""
    is_free: bool = False
    image_url: str = ""
    organizer_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""


def event_from_submission(submission) -> CanonicalEvent:
    """Build a CanonicalEvent from a BroadcastSubmission row."""
    return CanonicalEvent(
        title=submission.title,
        description=submission.description,
        start_datetime=_to_local(submission.start_datetime),
        end_datetime=_to_local(submission.end_datetime),
        all_day=submission.all_day,
        venue_name=submission.venue_name,
        address_line1=submission.address_line1,
        state=submission.state,
        zip=submission.zip,
        locality=list(submission.locality or []),
        categories=list(submission.categories or []),
        event_url=submission.event_url,
        ticket_url=submission.ticket_url,
        price=submission.price,
        is_free=submission.is_free,
        image_url=submission.image_url,
        organizer_name=submission.organizer_name,
        contact_email=submission.contact_email,
        contact_phone=submission.contact_phone,
    )
