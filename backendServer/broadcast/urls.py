from django.urls import path

from broadcast import views

app_name = "broadcast"

urlpatterns = [
    path("preview", views.preview, name="preview"),
    path("submit", views.submit, name="submit"),
    path("jobs/<uuid:job_id>", views.job_detail, name="job-detail"),
    path("jobs/<uuid:job_id>/retry", views.job_retry, name="job-retry"),
    path("jobs/<uuid:job_id>/submit-real", views.job_submit_real, name="job-submit-real"),
    path("jobs/<uuid:job_id>/cancel", views.job_cancel, name="job-cancel"),
    path("jobs/<uuid:job_id>/screenshots/<str:site_key>", views.job_screenshot, name="job-screenshot"),
    path("jobs/<uuid:job_id>/manual/<str:site_key>", views.job_manual_recipe, name="job-manual-recipe"),
    path("mock-form", views.mock_form, name="mock-form"),
    path("ai-autofill", views.ai_autofill, name="ai-autofill"),
]
