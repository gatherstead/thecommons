from django.urls import path
from . import views

app_name = 'devtools'
urlpatterns = [
    path('', views.playground, name='playground'),
    path('run', views.run_stream, name='run'),
    path('save', views.save_and_publish, name='save'),
]
