from django.urls import path

from . import views

urlpatterns = [
    path("", views.getAll, name="events"),
    path("towns/", views.getTowns, name="towns"),
    path("categories/", views.getCategories, name="categories"),
    path("me/profile", views.getMyProfile, name="my-profile"),
    path("me/events", views.getMyEvents, name="my-events"),
    path("staged/<int:event_id>", views.manageStagedEvent, name="manage-staged-event"),
    path("<uuid:event_id>", views.getOne, name="one-event"),
    path("create", views.createEvent, name="create-event"),
]
