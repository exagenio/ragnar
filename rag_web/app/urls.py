from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

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
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/",
        views.subtopic_dashboard,
        name="subtopic_dashboard",
    ),
    # path(
    #     "projects/<int:project_id>/report/<int:report_id>/sections/<slug:section>/subsections/<slug:subsection>/topics/",
    #     views.generate_subsection_topics_view,
    #     name="generate_subsection_topics",
    # ),
    # path(
    #     "projects/<int:project_id>/report/<int:report_id>/sections/<slug:section>/subsections/<slug:subsection>/topics/view/",
    #     views.view_subsection_topics,
    #     name="view_subsection_topics",
    # ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/<int:topic_id>/plan/",
        views.generate_topic_analysis_plan_view,
        name="topic_analysis_plan",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/overview/",
        views.topic_overview,
        name="topic_overview",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/topics/generate/",
        views.generate_topics,
        name="generate_topics",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/topics/view/",
        views.view_topics,
        name="view_topics",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/content/generate/",
        views.generate_subsection_content_view,
        name="generate_subsection_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/sections/<int:section_id>/content/generate/",
        views.generate_section_content_view,
        name="generate_section_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/<int:topic_id>/content/",
        views.generate_topic_content_view,
        name="topic_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/generate-document/",
        views.generate_document_view,
        name="generate_document",
    ),
    path(
        "projects/<int:project_id>/reports/<int:report_id>/subsections/<int:subsection_id>/auto-generate/",
        views.trigger_auto_generate_subsection,
        name="trigger_auto_generate_subsection",
    ),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
