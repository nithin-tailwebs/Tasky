from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from boards.views_me import MyTasksView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("boards.urls")),
    path("api/", include("projects.urls")),
    path("api/me/tasks/", MyTasksView.as_view(), name="my-tasks"),
    # Last on purpose. Registered any earlier this swallows /api/ and /admin/.
    # The negative lookahead is belt and braces — routing already tries the
    # patterns above first — but it keeps the intent explicit and makes the
    # shadowing test below meaningful.
    re_path(
        r"^(?!api/|admin/|static/).*$",
        TemplateView.as_view(template_name="index.html"),
        name="spa",
    ),
]
