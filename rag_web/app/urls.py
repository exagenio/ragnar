from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from app.views import metadata_views, project_views, sub_sect_views, topic_views, report_views, evalu_views

urlpatterns = [
    path("", metadata_views.create_project_and_connect_db, name="project_create"),
    path("projects/<int:project_id>/", metadata_views.project_detail, name="project_detail"),
    path(
        "projects/<int:project_id>/select-tables/",
        metadata_views.select_tables,
        name="select_tables",
    ),
    path(
        "projects/<int:project_id>/introspect-columns/",
        metadata_views.column_introspection,
        name="column_introspection",
    ),
    path(
        "projects/<int:project_id>/sample-rows/",
        metadata_views.row_sampling,
        name="row_sampling",
    ),
    path(
        "projects/<int:project_id>/generate-metadata/",
        metadata_views.metadata_generation,
        name="metadata_generation",
    ),
    path(
        "projects/<int:project_id>/metadata/<str:table_name>/review/",
        metadata_views.review_metadata,
        name="review_metadata",
    ),
    path(
        "projects/<int:project_id>/report/start/",
        project_views.start_report,
        name="start_report",
    ),
    path(
        "reports/<int:report_id>/outline/review/",
        project_views.review_outline,
        name="review_outline",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/",
        sub_sect_views.subtopic_dashboard,
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
        topic_views.generate_topic_analysis_plan_view,
        name="topic_analysis_plan",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/overview/",
        topic_views.topic_overview,
        name="topic_overview",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/topics/generate/",
        sub_sect_views.generate_topics,
        name="generate_topics",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/topics/view/",
        sub_sect_views.view_topics,
        name="view_topics",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/content/generate/",
        report_views.generate_subsection_content_view,
        name="generate_subsection_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/sections/<int:section_id>/content/generate/",
        report_views.generate_section_content_view,
        name="generate_section_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/<int:topic_id>/content/",
        topic_views.generate_topic_content_view,
        name="topic_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/generate-document/",
        report_views.generate_document_view,
        name="generate_document",
    ),
    path(
        "projects/<int:project_id>/reports/<int:report_id>/subsections/<int:subsection_id>/auto-generate/",
        report_views.trigger_auto_generate_subsection,
        name="trigger_auto_generate_subsection",
    ),
    path(
        "projects/<int:project_id>/evaluation/",
        evalu_views.evaluation_dashboard_view,
        name="evaluation_dashboard_view",
    ),
    path(
    "projects/<int:project_id>/evaluation/export/",
    evalu_views.export_evaluation_doc,
    name="export_evaluation_doc",
),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
