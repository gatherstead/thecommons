from django.urls import path

from . import views

urlpatterns = [
    #URL: events/
    path("", views.getAll, name="events"),
    #URL: events/<uuid:event_id>
    path("<uuid:event_id>", views.getOne, name="one-event"),
    #URL: events/create
    path("create", views.createEvent, name="create-event"),
]