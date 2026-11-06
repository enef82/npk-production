from django.contrib import admin
from django.urls import path

from config.api import api
from config.health import health_check, healthz

urlpatterns = [
    path("health/", health_check, name="health"),
    path("healthz", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
]
