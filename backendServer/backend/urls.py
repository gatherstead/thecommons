"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""

from django.contrib import admin
from django.urls import include, path

from ingestion.views import admin_docs, cron_ingest, pipeline_docs, publish_approved_admin, publish_approved_events

urlpatterns = [
    path("events/", include("events.urls")),
    path("admin/docs/pipeline-docs/", pipeline_docs, name="pipeline-docs"),
    path("admin/docs/admin-docs/", admin_docs, name="admin-docs"),
    path("admin/docs/publish-approved/", publish_approved_admin, name="publish-approved-admin"),
    path("admin/", admin.site.urls),
    path("api/cron/ingest", cron_ingest, name="cron-ingest"),
    path("api/events/publish-approved", publish_approved_events, name="publish-approved-events"),
]
