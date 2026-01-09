from django.urls import path
from . import views

urlpatterns = [
    path("", views.create_project_and_connect_db, name="project_create"),
    path("projects/<int:project_id>/", views.project_detail, name="project_detail"),
    path(
        "projects/<int:project_id>/select-tables/",
        views.select_tables,
        name="select_tables",
    ),
    path(
        "projects/<int:project_id>/introspect-columns/",
        views.column_introspection,
        name="column_introspection",
    ),
    path(
        "projects/<int:project_id>/sample-rows/",
        views.row_sampling,
        name="row_sampling",
    ),
]
