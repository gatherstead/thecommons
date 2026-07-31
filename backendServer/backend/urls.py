"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from events.views import (
    business_detail,
    businesses,
    me,
    my_business,
    newsletter_manage,
    subscribe,
)
from ingestion.views import (
    admin_docs,
    cron_ingest,
    direct_submit,
    pipeline_docs,
    publish_approved_admin,
    publish_approved_events,
)

urlpatterns = [
    path("events/", include("events.urls")),
    path("broadcast/", include("broadcast.urls")),
    path("admin/docs/pipeline-docs/", pipeline_docs, name="pipeline-docs"),
    path("admin/docs/admin-docs/", admin_docs, name="admin-docs"),
    path("admin/docs/publish-approved/", publish_approved_admin, name="publish-approved-admin"),
    path("admin/", admin.site.urls),
    path("api/cron/ingest", cron_ingest, name="cron-ingest"),
    path("api/events/publish-approved", publish_approved_events, name="publish-approved-events"),
    path("api/events/direct-submit", direct_submit, name="direct-submit"),
    path("newsletter/subscribe", subscribe, name="subscribe"),
    path("newsletter/manage", newsletter_manage, name="newsletter-manage"),
    path("auth/me", me, name="auth-me"),
    path("businesses", businesses, name="businesses"),
    path("businesses/me", my_business, name="my-business"),
    path("businesses/<uuid:business_id>", business_detail, name="business-detail"),
]

if settings.DEBUG:
    urlpatterns += [path("devtools/", include("devtools.urls"))]
