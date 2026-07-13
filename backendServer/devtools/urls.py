from django.urls import path

from . import views

app_name = "devtools"
urlpatterns = [
    path("", views.index, name="index"),
    path("ingestion-playground", views.playground, name="playground"),
    path("run", views.run_stream, name="run"),
    path("save", views.save_and_publish, name="save"),
    path("add-source", views.add_source, name="add_source"),
    path("publish-events-only", views.publish_events_only, name="publish_events_only"),
]
