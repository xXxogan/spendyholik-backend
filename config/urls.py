"""Root URL router — mounts the ``/api/v1`` module routers."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1 = [
    path("", include("accounts.interfaces.urls")),
    path("", include("finances.interfaces.urls")),
    path("", include("goals.interfaces.urls")),
    path("", include("recurring.interfaces.urls")),
    path("", include("debts.interfaces.urls")),
    path("", include("analytics.interfaces.urls")),
    path("", include("notifications.interfaces.urls")),
    path("", include("core.interfaces.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include(api_v1)),
    path("", include("django_prometheus.urls")),
]
