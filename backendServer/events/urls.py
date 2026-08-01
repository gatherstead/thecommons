from django.urls import path

from . import views

urlpatterns = [
    path("", views.get_all, name="events"),
    path("towns/", views.get_towns, name="towns"),
    path("categories/", views.get_categories, name="categories"),
    path("me/profile", views.get_my_profile, name="my-profile"),
    path("me/events", views.get_my_events, name="my-events"),
    path("staged/<int:event_id>", views.manage_staged_event, name="manage-staged-event"),
    path("<uuid:event_id>", views.get_one, name="one-event"),
    path("create", views.create_event, name="create-event"),
]
