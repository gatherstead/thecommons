from django.urls import path

from . import views

urlpatterns = [
    path("newsletter/subscribe", views.subscribe, name="subscribe"),
    path("newsletter/manage", views.newsletter_manage, name="newsletter-manage"),
]
