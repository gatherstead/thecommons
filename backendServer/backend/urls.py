"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("events/", include("events.urls")),
    path("", include("accounts.urls")),
    path("broadcast/", include("broadcast.urls")),
    path("", include("ingestion.urls")),
    path("admin/", admin.site.urls),
    path("", include("newsletter.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("devtools/", include("devtools.urls"))]
    # nginx owns /media/ in Docker/prod; this only serves MEDIA_ROOT for `runserver`.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
