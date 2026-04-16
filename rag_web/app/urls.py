from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as django_auth_views
from django.contrib.auth.decorators import login_required
from django.urls import path

from app.views import (
    auth_views,
    evalu_views,
    metadata_views,
    project_views,
    report_views,
    sub_sect_views,
    topic_views,
)


def protected(view):
    return login_required(view, login_url="login")


urlpatterns = [
    path("login/", auth_views.login_view, name="login"),
    path("register/", auth_views.register, name="register"),
    path(
        "logout/",
        django_auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path("", protected(metadata_views.create_project_and_connect_db), name="project_create"),
    path(
        "projects/<int:project_id>/",
        protected(metadata_views.project_detail),
        name="project_detail",
    ),
    path(
        "projects/<int:project_id>/select-tables/",
        protected(metadata_views.select_tables),
        name="select_tables",
    ),
    path(
        "projects/<int:project_id>/introspect-columns/",
        protected(metadata_views.column_introspection),
        name="column_introspection",
    ),
    path(
        "projects/<int:project_id>/sample-rows/",
        protected(metadata_views.row_sampling),
        name="row_sampling",
    ),
    path(
        "projects/<int:project_id>/generate-metadata/",
        protected(metadata_views.metadata_generation),
        name="metadata_generation",
    ),
    path(
        "projects/<int:project_id>/metadata/<str:table_name>/review/",
        protected(metadata_views.review_metadata),
        name="review_metadata",
    ),
    path(
        "projects/<int:project_id>/report/start/",
        protected(project_views.start_report),
        name="start_report",
    ),
    path(
        "projects/<int:project_id>/settings/",
        protected(project_views.project_settings),
        name="project_settings",
    ),
    path(
        "reports/<int:report_id>/outline/review/",
        protected(project_views.review_outline),
        name="review_outline",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/",
        protected(sub_sect_views.subtopic_dashboard),
        name="subtopic_dashboard",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/<int:topic_id>/plan/",
        protected(topic_views.generate_topic_analysis_plan_view),
        name="topic_analysis_plan",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/overview/",
        protected(topic_views.topic_overview),
        name="topic_overview",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/topics/generate/",
        protected(sub_sect_views.generate_topics),
        name="generate_topics",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/topics/view/",
        protected(sub_sect_views.view_topics),
        name="view_topics",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/subsections/<int:subsection_id>/content/generate/",
        protected(report_views.generate_subsection_content_view),
        name="generate_subsection_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/sections/<int:section_id>/content/generate/",
        protected(report_views.generate_section_content_view),
        name="generate_section_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/topics/<int:topic_id>/content/",
        protected(topic_views.generate_topic_content_view),
        name="topic_content",
    ),
    path(
        "projects/<int:project_id>/report/<int:report_id>/generate-document/",
        protected(report_views.generate_document_view),
        name="generate_document",
    ),
    path(
        "projects/<int:project_id>/reports/<int:report_id>/subsections/<int:subsection_id>/auto-generate/",
        protected(report_views.trigger_auto_generate_subsection),
        name="trigger_auto_generate_subsection",
    ),
    path(
        "projects/<int:project_id>/evaluation/",
        protected(evalu_views.evaluation_dashboard_view),
        name="evaluation_dashboard_view",
    ),
    path(
        "projects/<int:project_id>/evaluation/export/",
        protected(evalu_views.export_evaluation_doc),
        name="export_evaluation_doc",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
