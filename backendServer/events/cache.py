"""Caching helpers for the hot public read endpoints.

The event list is cached under a version-keyed scheme: each cache key embeds the
current list version, and a write bumps the version so subsequent reads miss and
repopulate (old entries fall out via TTL). This works with Django's stdlib
RedisCache backend, which has no `delete_pattern`. Towns and categories are
near-static, so they use plain keys with a long TTL.
"""

import hashlib

from django.core.cache import cache

EVENTS_LIST_VERSION_KEY = "events:list:version"
EVENTS_LIST_TTL = 60  # seconds — community freshness without hammering Neon

TOWNS_CACHE_KEY = "events:towns"
CATEGORIES_CACHE_KEY = "events:categories"
STATIC_TTL = 60 * 60  # 1 hour — refreshed only via admin/pipeline


def _events_list_version():
    version = cache.get(EVENTS_LIST_VERSION_KEY)
    if version is None:
        # add() is a no-op if another request set it first, so re-read.
        cache.add(EVENTS_LIST_VERSION_KEY, 1)
        version = cache.get(EVENTS_LIST_VERSION_KEY) or 1
    return version


def events_list_key(query_params):
    """Deterministic key for an event-list request, stable across equivalent params."""
    items = sorted((k, v) for k in query_params for v in query_params.getlist(k))
    raw = "&".join(f"{k}={v}" for k, v in items)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"events:list:v{_events_list_version()}:{digest}"


def invalidate_events_list():
    """Bump the list version so all cached event-list pages are bypassed."""
    try:
        cache.incr(EVENTS_LIST_VERSION_KEY)
    except ValueError:
        # Key absent → nothing is cached under any version yet.
        cache.add(EVENTS_LIST_VERSION_KEY, 1)


def invalidate_towns():
    cache.delete(TOWNS_CACHE_KEY)


def invalidate_categories():
    cache.delete(CATEGORIES_CACHE_KEY)
