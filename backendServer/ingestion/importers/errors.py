"""Typed refusal signalling shared by the importers and the devtools probe.

The scraper/http guard paths used to `return []`, which the poll loop could not
tell apart from a successful fetch that found nothing new. Raising instead lets
callers record *why* a source produced no events -- see `SourceRun.status`
("refused" vs "failed") and the devtools probe's named error frames.
"""

# Reason codes. Kept as plain strings so they can be stored in
# `SourceRun.error_message` and emitted in SSE frames without translation.
REFUSAL_NON_PUBLIC_URL = "non_public_url"
REFUSAL_UNKNOWN_SCRAPER_KEY = "unknown_scraper_key"
REFUSAL_EMPTY_FETCH = "empty_fetch"

# Probe-only: the poll loop never reaches these (it filters to pollable source
# types up front), but the devtools probe can be pointed at any source row.
REFUSAL_NOTHING_TO_POLL = "nothing_to_poll"
REFUSAL_UNKNOWN_SOURCE_TYPE = "unknown_source_type"

REFUSAL_REASONS = (
    REFUSAL_NON_PUBLIC_URL,
    REFUSAL_UNKNOWN_SCRAPER_KEY,
    REFUSAL_EMPTY_FETCH,
    REFUSAL_NOTHING_TO_POLL,
    REFUSAL_UNKNOWN_SOURCE_TYPE,
)


class SourceRefused(Exception):
    """A guard declined to poll a source. Carries a `REFUSAL_*` reason code."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)
