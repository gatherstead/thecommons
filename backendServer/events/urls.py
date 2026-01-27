from django.urls import path

from . import views

urlpatterns = [
    path("events", views.getAll, name="events"),
    path("event/<uuid:event_id>", views.getOne, name="one-event")
]