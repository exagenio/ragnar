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
    path(
        "projects/<int:project_id>/generate-metadata/",
        views.metadata_generation,
        name="metadata_generation",
    ),
    path(
        "projects/<int:project_id>/metadata/<str:table_name>/review/",
        views.review_metadata,
        name="review_metadata",
    ),
    path(
        "projects/<int:project_id>/report/start/",
        views.start_report,
        name="start_report",
    ),
    path(
        "reports/<int:report_id>/outline/review/",
        views.review_outline,
        name="review_outline",
    ),
]
