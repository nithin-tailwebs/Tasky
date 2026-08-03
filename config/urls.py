from django.contrib import admin
from django.urls import include, path

from boards.views_me import MyTasksView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("boards.urls")),
    path("api/me/tasks/", MyTasksView.as_view(), name="my-tasks"),
]
