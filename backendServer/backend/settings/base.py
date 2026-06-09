import os
from pathlib import Path
from dotenv import load_dotenv
from corsheaders.defaults import default_headers

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    'unfold',
    'corsheaders',
    'rest_framework',
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "events.apps.EventsConfig",
    "ingestion.apps.IngestionConfig",
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
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

CSRF_TRUSTED_ORIGINS = [
    o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

CORS_ALLOW_HEADERS = list(default_headers) + [
    "content-type",
    "authorization",
    "x-csrftoken",
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
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles_build', 'static')

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "events": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "ingestion": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
CRON_SECRET = os.environ.get('CRON_SECRET', '')
THE_COMMONS_API_KEY = os.environ.get('THE_COMMONS_API_KEY', '')

BETTER_AUTH_JWKS_URL = os.environ.get('BETTER_AUTH_JWKS_URL', '')
BETTER_AUTH_ISSUER = os.environ.get('BETTER_AUTH_ISSUER', '')
BETTER_AUTH_AUDIENCE = os.environ.get('BETTER_AUTH_AUDIENCE', '')

UNFOLD = {
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
                    {"title": "Event Sources", "link": "/admin/ingestion/eventsource/", "icon": "rss_feed"},
                    {"title": "Raw Events", "link": "/admin/ingestion/rawevent/", "icon": "inbox"},
                    {"title": "Staged Events", "link": "/admin/ingestion/stagedevent/", "icon": "pending_actions"},
                    {"title": "Publish Approved", "link": "/admin/docs/publish-approved/", "icon": "publish"},
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
                    {"title": "User Profiles", "link": "/admin/events/userprofile/", "icon": "manage_accounts"},
                ],
            },
            {
                "title": "Documentation",
                "items": [
                    {"title": "Admin Docs", "link": "/admin/docs/admin-docs/", "icon": "help"},
                    {"title": "Pipeline Docs", "link": "/admin/docs/pipeline-docs/", "icon": "menu_book"},
                ],
            },
        ],
    },
}
