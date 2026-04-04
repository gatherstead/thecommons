from django.urls import path

from . import views

urlpatterns = [
    path("", views.getAll, name="events"),
    path("towns/", views.getTowns, name="towns"),
    path("<uuid:event_id>", views.getOne, name="one-event"),
    path("create", views.createEvent, name="create-event"),
]