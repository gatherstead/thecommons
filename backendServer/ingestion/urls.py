from django.urls import path

from . import views

urlpatterns = [
    path("admin/docs/pipeline-docs/", views.pipeline_docs, name="pipeline-docs"),
    path("admin/docs/admin-docs/", views.admin_docs, name="admin-docs"),
    path(
        "admin/docs/publish-approved/",
        views.publish_approved_admin,
        name="publish-approved-admin",
    ),
    path("api/cron/ingest", views.cron_ingest, name="cron-ingest"),
    path(
        "api/events/publish-approved",
        views.publish_approved_events,
        name="publish-approved-events",
    ),
    path("api/events/direct-submit", views.direct_submit, name="direct-submit"),
]
