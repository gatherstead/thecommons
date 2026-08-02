import os
from pathlib import Path
from typing import Any

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "unfold",
    "corsheaders",
    "rest_framework",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts.apps.AccountsConfig",
    "events.apps.EventsConfig",
    "newsletter.apps.NewsletterConfig",
    "ingestion.apps.IngestionConfig",
    "broadcast.apps.BroadcastConfig",
    "django_celery_beat",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "https://www.thecommons.town",
] + [o for o in os.getenv("CORS_EXTRA_ORIGINS", "").split(",") if o]

CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

CORS_ALLOW_HEADERS = list(default_headers) + [
    "content-type",
    "authorization",
    "x-csrftoken",
    "x-broadcast-access-code",
]

APPEND_SLASH = False

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "ingestion" / "templates", BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles_build", "static")

# Self-hosted event image uploads (broadcast). MEDIA_ROOT defaults to a path
# inside the repo checkout for local dev, but prod sets MEDIA_ROOT in .env to
# a path outside the checkout (mirrors BROADCAST_SCREENSHOT_DIR) so `git pull`
# during deploy can never touch uploaded files. Served by nginx in prod, never
# by Django — see DEPLOY.md for the /media/ alias.
MEDIA_URL = "/media/"
MEDIA_ROOT = os.getenv("MEDIA_ROOT", os.path.join(BASE_DIR, "media"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "events": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "ingestion": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "broadcast": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

# ── Broadcast (event syndication) ────────────────────────────────────────────
# RATELIMIT_IP_META_KEY = "HTTP_X_REAL_IP" is set in prod.py only — nginx sets
# that header in production (proxy_set_header X-Real-IP $remote_addr;) because
# it proxies to gunicorn over a Unix socket, which leaves REMOTE_ADDR empty.
# `manage.py runserver` in dev populates REMOTE_ADDR directly and never sets
# X-Real-IP, so overriding this key here breaks ratelimit locally.
BROADCAST_HEADLESS = os.getenv("BROADCAST_HEADLESS", "true").lower() != "false"
BROADCAST_DRY_RUN_DEFAULT = os.getenv("BROADCAST_DRY_RUN_DEFAULT", "false").lower() == "true"
BROADCAST_MAX_CONCURRENCY = int(os.getenv("BROADCAST_MAX_CONCURRENCY", "1"))
BROADCAST_SCREENSHOT_DIR = os.getenv(
    "BROADCAST_SCREENSHOT_DIR", str(BASE_DIR / "broadcast_artifacts" / "screenshots")
)
BROADCAST_DOWNLOAD_DIR = os.getenv(
    "BROADCAST_DOWNLOAD_DIR", str(BASE_DIR / "broadcast_artifacts" / "downloads")
)
BROADCAST_TIMEOUT_MS = int(os.getenv("BROADCAST_TIMEOUT_MS", "30000"))

# ── Ingestion scraper (Playwright page render) ───────────────────────────────
INGEST_SCRAPER_HEADLESS = os.getenv("INGEST_SCRAPER_HEADLESS", "true").lower() != "false"
INGEST_SCRAPER_TIMEOUT_MS = int(os.getenv("INGEST_SCRAPER_TIMEOUT_MS", "30000"))
INGEST_SCRAPER_USER_AGENT = os.getenv(
    "INGEST_SCRAPER_USER_AGENT", "Mozilla/5.0 (compatible; TheCommons/1.0)"
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
THE_COMMONS_API_KEY = os.environ.get("THE_COMMONS_API_KEY", "")

# ── Redis / Celery ───────────────────────────────────────────────────────────
# One self-hosted Redis: DB 0 = broker + result backend, DB 1 reserved for a
# future Django cache (not wired yet). Prod sets a password-protected URL in .env.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = False  # tests override via @override_settings
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Upper bound on beat's sleep between ticks — it still wakes exactly on time for
# actual due tasks (scrape 3:30am, ingest 4:00am, digest), this only caps how often
# it re-polls the DB for schedule changes in between, to reduce Neon wake-ups.
#
# Trade-off: DatabaseScheduler keeps `PeriodicTask.last_run_at` in memory and only
# flushes it to Postgres on a sync. With beat_sync_every left at its default (0),
# the only other sync trigger is time-based (every 3 min, capped by this interval),
# so last_run_at can visibly lag reality by up to 6h until CELERY_BEAT_SYNC_EVERY
# (below) forces a flush after every task send instead. See docs/ingestion-monitoring.md
# "Beat scheduler: last_run_at persistence lag" for the full incident writeup.
CELERY_BEAT_MAX_LOOP_INTERVAL = 6 * 60 * 60
# Force a DB sync after every single task send (celery/beat.py Scheduler.should_sync:
# `self.sync_every_tasks and self._tasks_since_sync >= self.sync_every_tasks`), maps to
# app.conf.beat_sync_every via Scheduler.__init__ (celery/beat.py:262-264). Without this,
# a task firing within 180s of the prior sync (beat_sync_every default 0 disables the
# task-count trigger, and the time-based trigger is `sync_every=180`) leaves
# last_run_at stuck in memory until the next sync opportunity — up to 6h away given
# CELERY_BEAT_MAX_LOOP_INTERVAL above. Costs one UPDATE per task fire; does not touch
# the loop interval or Neon poll rate.
CELERY_BEAT_SYNC_EVERY = 1
CELERY_TIMEZONE = "UTC"

# Headless-Chrome scraping is memory-heavy — pin it to its own queue drained by a
# dedicated, memory-capped worker (deploy/scrape-worker.service) so it never shares
# the default worker with digests/ingestion.
#
# The two broadcast tasks below share this SAME `broadcast` queue, drained by a
# SINGLE `-c 1` worker. That's load-bearing: recover_broadcast_orphans assumes any
# submission still in 'running' status is orphaned, which only holds if it can
# never run while process_broadcast_queue is mid-drain on another worker.
CELERY_TASK_ROUTES = {
    "ingestion.tasks.scrape_all_sources_task": {"queue": "scrape"},
    "broadcast.tasks.process_broadcast_queue": {"queue": "broadcast"},
    "broadcast.tasks.recover_broadcast_orphans": {"queue": "broadcast"},
}

# Read-endpoint cache on Redis DB 1 (broker is DB 0). dev.py swaps this for a
# local-memory backend during tests so the suite needs no running Redis.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1"),
    }
}

# Sessions (admin-only) live in the Redis cache (DB 1), not the Neon django_session
# table, so idle Django holds no DB-backed session traffic — trade-off: a Redis
# flush logs admins out, which is acceptable since sessions here are admin-only.
SESSION_ENGINE = "django.contrib.sessions.backends.cache"

BETTER_AUTH_JWKS_URL = os.environ.get("BETTER_AUTH_JWKS_URL", "")
BETTER_AUTH_ISSUER = os.environ.get("BETTER_AUTH_ISSUER", "")
BETTER_AUTH_AUDIENCE = os.environ.get("BETTER_AUTH_AUDIENCE", "")

UNFOLD: dict[str, Any] = {
    "SITE_TITLE": "The Commons Admin",
    "SITE_HEADER": "The Commons Admin",
    "SITE_SUBHEADER": None,
    "SITE_URL": "https://www.thecommons.town",
    "SITE_SYMBOL": None,
    "SITE_LOGO": None,
    "SITE_FAVICONS": [],
    "SHOW_HEADER_SEARCH": True,
    "SHOW_LANGUAGES": False,
    "SIDEBAR": {
        "navigation": [
            {
                "title": "Ingestion",
                "items": [
                    {
                        "title": "Event Sources",
                        "link": "/admin/ingestion/eventsource/",
                        "icon": "rss_feed",
                    },
                    {"title": "Raw Events", "link": "/admin/ingestion/rawevent/", "icon": "inbox"},
                    {
                        "title": "Staged Events",
                        "link": "/admin/ingestion/stagedevent/",
                        "icon": "pending_actions",
                    },
                    {
                        "title": "Publish Approved",
                        "link": "/admin/docs/publish-approved/",
                        "icon": "publish",
                    },
                ],
            },
            {
                "title": "Events",
                "items": [
                    {"title": "Published Events", "link": "/admin/events/event/", "icon": "event"},
                    {"title": "Tags", "link": "/admin/events/tag/", "icon": "label"},
                    {"title": "Towns", "link": "/admin/events/town/", "icon": "location_city"},
                ],
            },
            {
                "title": "Users",
                "items": [
                    {"title": "Users", "link": "/admin/auth/user/", "icon": "person"},
                    {
                        "title": "User Profiles",
                        "link": "/admin/accounts/userprofile/",
                        "icon": "manage_accounts",
                    },
                ],
            },
            {
                "title": "Documentation",
                "items": [
                    {"title": "Admin Docs", "link": "/admin/docs/admin-docs/", "icon": "help"},
                    {
                        "title": "Pipeline Docs",
                        "link": "/admin/docs/pipeline-docs/",
                        "icon": "menu_book",
                    },
                ],
            },
        ],
    },
}
