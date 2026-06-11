"""Canonical event schema — the single shape adapters receive.

Decoupled from the ORM row so adapters never touch the database.
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CanonicalEvent:
    title: str
    description: str
    start_datetime: datetime
    venue_name: str
    address_line1: str
    city: str
    zip: str
    locality: str
    categories: list[str] = field(default_factory=list)
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
        start_datetime=submission.start_datetime,
        end_datetime=submission.end_datetime,
        all_day=submission.all_day,
        venue_name=submission.venue_name,
        address_line1=submission.address_line1,
        city=submission.city,
        state=submission.state,
        zip=submission.zip,
        locality=submission.locality,
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
