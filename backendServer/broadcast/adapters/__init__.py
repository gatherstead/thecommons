"""Adapter registry: site_key → adapter instance.

Site metadata (URL, eligibility, auth) lives in code with the adapter so the
rules and the script version together. Tier 2 (auth) adapters are added here
only after a ToS review (design doc §13).
"""
import os

from broadcast.adapters._mock import MockSiteAdapter
from broadcast.adapters.abc11_community import Abc11CommunityAdapter
from broadcast.adapters.chapelboro import ChapelboroAdapter
from broadcast.adapters.chatham_arts import ChathamArtsAdapter
from broadcast.adapters.chatham_chamber import ChathamChamberAdapter
from broadcast.adapters.explore_pittsboro import ExplorePittsboroAdapter
from broadcast.adapters.fun4raleighkids import Fun4RaleighKidsAdapter
from broadcast.adapters.indy_week import IndyWeekAdapter
from broadcast.adapters.shop_pittsboro import ShopPittsboroAdapter
from broadcast.adapters.triangle_on_the_cheap import TriangleOnTheCheapAdapter
from broadcast.adapters.triangle_weekender import TriangleWeekenderAdapter
from broadcast.adapters.visit_raleigh import VisitRaleighAdapter

_TIER1 = [
    TriangleOnTheCheapAdapter(),
    TriangleWeekenderAdapter(),
    IndyWeekAdapter(),
    Abc11CommunityAdapter(),
    VisitRaleighAdapter(),
    Fun4RaleighKidsAdapter(),
    ChapelboroAdapter(),
    ExplorePittsboroAdapter(),
    ChathamChamberAdapter(),
    ShopPittsboroAdapter(),
    ChathamArtsAdapter(),
]

_MOCK = MockSiteAdapter()


def registry() -> dict:
    """All known adapters by key, including the local mock when enabled."""
    adapters = {a.key: a for a in _TIER1}
    if os.environ.get("BROADCAST_ENABLE_MOCK", "").lower() in ("1", "true", "yes"):
        adapters[_MOCK.key] = _MOCK
    return adapters


def enabled_adapters() -> list:
    return list(registry().values())


def get_adapter(site_key: str):
    return registry().get(site_key)
