from django.urls import path

from apps.bot import views

app_name = "bot"

urlpatterns = [
    path("<str:webhook_secret>/", views.webhook, name="webhook"),
]
