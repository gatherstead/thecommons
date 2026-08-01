from django.urls import path

from .views import business_detail, businesses, me, my_business

urlpatterns = [
    path("auth/me", me, name="auth-me"),
    path("businesses", businesses, name="businesses"),
    path("businesses/me", my_business, name="my-business"),
    path("businesses/<uuid:business_id>", business_detail, name="business-detail"),
]
