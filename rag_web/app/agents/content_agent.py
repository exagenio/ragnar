# Standard library imports
import json

# Third-party imports
from django.utils.text import slugify
from django.db.models import Prefetch

# Local imports
from app.models import (
    Report,
    ReportOutline,
    Section,
    SubSection,
    Topic,
    TopicAnalysisPlan,
    SubSectionContent,
    SectionContent,
    TopicContent,
)
from app.services.document_generator import generate_report_document

from app.services.outline_generation.report_outline_generator import generate_report_outline
from app.services.sub_sec_gen.subsection_topic_generator import generate_subsection_topics
from app.services.metadata_generation.schema_context_builder import build_schema_context
from app.services.topic_gen.topic_analysis_plan_generator import generate_topic_analysis_plan
from app.services.topic_gen.topic_analysis_plan_generator import normalize_topic_analysis_plan
from app.services.topic_gen.topic_content_generator import generate_topic_content
from app.services.sub_sec_gen.sub_section_content_generator import generate_subsection_content
from app.services.section_content_generator import generate_section_content
from app.services.topic_gen.visual_gen.placeholder_normalizer import normalize_placeholders
from app.services.topic_gen.topic_content_repair import repair_topic_content
from app.services.metadata_generation.metadata_retriever import retrieve_multi_table_metadata


class ContentAgent:

    def start_report(self, project, data):
        """Start report"""

        # Generate outline and create report
        outline = generate_report_outline(
            data=data,
            project=project,
            project_id=project.id,
        )

        report = Report.objects.create(
            project=project,
            title=outline["report_title"],
            industry=data["industry"],
            report_type=data["report_type"],
            audience=data["audience"],
            purpose=data["purpose"],
            focus_areas=data.get("focus_areas", ""),
            additional_notes=data.get("additional_notes", ""),
        )

        ReportOutline.objects.create(
            report=report,
            outline_json=outline,
        )

        return report
    
    def update_outline(self, outline_obj, updated_outline):
        """Update outline"""

        outline_obj.outline_json = updated_outline
        outline_obj.save()

        return outline_obj


    def approve_outline(self, report):
        """Approve outline"""

        outline_obj = report.outline
        outline_obj.approved = True
        outline_obj.save()

        report.status = "outline_approved"
        report.outline_approved = True
        report.save()

        outline_data = outline_obj.outline_json

        # Create sections and subsections from outline
        for section_data in outline_data.get("sections", []):
            section_title = section_data.get("section_title", "").strip()

            if not section_title:
                continue

            section_obj, _ = Section.objects.get_or_create(
                report=report,
                title=section_title,
                is_sub_sec_appvroved=True,
            )

            for subsection_title in section_data.get("subsections", []):

                subsection_title = subsection_title.strip()

                if not subsection_title:
                    continue

                SubSection.objects.get_or_create(
                    section=section_obj,
                    title=subsection_title,
                    report=report,
                )

        return report
    
    def generate_topics(self, report, subsection, section, project_id):
        """Generate topics"""

        # Build context and generate topics
        context = {
            "industry": report.industry,
            "report_type": report.report_type,
            "audience": report.audience,
            "purpose": report.purpose,
            "section_title": section.title,
            "subsection_title": subsection.title,
        }

        result = generate_subsection_topics(
            context=context,
            project=report.project,
            project_id=project_id,
        )

        print("topics")
        print(result)

        for topic_title in result.get("topics", []):
            Topic.objects.create(
                subsection=subsection,
                report=report,
                title=topic_title,
            )

    def save_topics(self, report, subsection, submitted_titles):
        """Save topics"""

        # Sync topics with submitted list
        existing_topics = {t.title: t for t in subsection.topics.all()}

        for title, topic_obj in existing_topics.items():
            if title not in submitted_titles:
                topic_obj.delete()

        for title in submitted_titles:
            Topic.objects.update_or_create(
                subsection=subsection,
                report=report,
                title=title,
                defaults={"is_approved": False},
            )

    def approve_topics(self, subsection, section):
        """Approve topics"""

        Topic.objects.filter(subsection=subsection).update(is_approved=True)

        subsection.is_topics_approved = True
        subsection.save()

        section.is_sub_sec_appvroved = True
        section.save()

    def build_schema_context(self, project):
        """Build schema context"""
        return build_schema_context(project)
    
    def generate_topic_analysis_plan(self, project, report, topic):
        """Generate topic analysis plan"""

        subsection = topic.subsection
        section = subsection.section

        schema_context = self.build_schema_context(project)

        plan_obj, created = TopicAnalysisPlan.objects.get_or_create(
            report=report,
            topic=topic,
            defaults={"plan_json": {}},
        )

        # Generate plan if not exists
        if not plan_obj.plan_json:

            context = {
                "industry": report.industry,
                "report_type": report.report_type,
                "audience": report.audience,
                "purpose": report.purpose,
                "section_title": section.title,
                "subsection_title": subsection.title,
                "topic_title": topic.title,
                "database_schema": schema_context,
            }

            plan = generate_topic_analysis_plan(context, project=project)
            plan = normalize_topic_analysis_plan(plan)

            plan_obj.plan_json = plan
            plan_obj.save()

        return plan_obj
    
    def update_topic_analysis_plan(self, plan_obj, topic, form_data, approve=False):
        """Update topic analysis plan"""


        plan = normalize_topic_analysis_plan(plan_obj.plan_json.copy())

        plan["intent"] = form_data.get("intent", "").strip()

        def collect_list(prefix):
            items = []
            i = 0

            while f"{prefix}_{i}" in form_data:
                val = form_data.get(f"{prefix}_{i}", "").strip()

                if val:
                    items.append(val)

                i += 1

            return items

        plan["required_elements"] = collect_list("required_elements")
        plan["business_questions"] = collect_list("business_questions")
        plan["visual_requirements"] = collect_list("visual_requirements")

        plan["data_requirements"] = json.loads(
            form_data.get("data_requirements", "[]")
        )

        plan_obj.plan_json = plan

        if approve:
            plan_obj.is_approved = True
            topic.is_approved = True
            topic.save()

        plan_obj.save()
        return plan

    def get_topic_content(self, topic):
        """Get topic content"""

        if not topic.is_approved:
            raise ValueError("Topic must be approved before content generation.")

        if not hasattr(topic, "analysis_plan") or not topic.analysis_plan.is_approved:
            raise ValueError("Topic analysis plan must be approved first.")

        content_obj, _ = TopicContent.objects.get_or_create(
            topic=topic,
            defaults={
                "content_json": {},
                "status": "draft",
                "iteration_count": 0,
            },
        )

        return content_obj
    
    def generate_topic_content(self, project, report, topic, content_obj):
        """Generate topic content"""

        content_obj.status = "in_progress"
        content_obj.save()

        precomputed = (content_obj.content_json or {}).get(
            "precomputed_sql_placeholders", []
        )

        normalized_plan = normalize_topic_analysis_plan(topic.analysis_plan.plan_json or {})

        # Generate and normalize content
        result = generate_topic_content(
            project=project,
            project_id=project.id,
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            section_title=topic.subsection.section.title,
            subsection_title=topic.subsection.title,
            topic_title=topic.title,
            topic_plan=normalized_plan,
            existing_content=content_obj.content_json or None,
            precomputed_sql_placeholders=precomputed, 
        )

        result = normalize_placeholders(result)

        content_obj.content_json = result
        content_obj.iteration_count = result.get("iteration_count", 0)
        content_obj.status = result.get("status", "draft")
        content_obj.save()

        return content_obj
    
    def get_subsection_content(self, subsection):
        """Get subsection content"""

        content_obj, _ = SubSectionContent.objects.get_or_create(
            subsection=subsection,
            defaults={
                "content_json": {},
                "status": "draft",
            },
        )

        return content_obj

    def validate_subsection_generation(self, subsection):
        """Validate subsection content generation prerequisites."""

        topics = list(
            subsection.topics.filter(is_approved=True).order_by("created_at")
        )

        if not topics:
            raise ValueError(
                "Approved topics are required before generating subsection content."
            )

        incomplete_topics = [
            topic.title
            for topic in topics
            if not hasattr(topic, "content") or topic.content.status != "generated"
        ]

        if incomplete_topics:
            raise ValueError(
                "All approved topic content must be generated first. Missing: "
                + ", ".join(incomplete_topics)
            )

        return topics

    def generate_subsection_content(
        self,
        project,
        report,
        subsection,
        topics,
        content_obj,
    ):
        """Generate subsection-level synthesized content."""

        content_obj.status = "in_progress"
        content_obj.save()

        topics_progress = self.collect_topics_progress(topics)

        result = generate_subsection_content(
            project=project,
            project_id=project.id,
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            report_title=report.title,
            section_title=subsection.section.title,
            subsection_title=subsection.title,
            topics_progress=topics_progress,
            metadata_context=retrieve_multi_table_metadata(
                project=project,
                primary_query=(
                    f"{report.title} {subsection.section.title} {subsection.title} "
                    f"{' '.join(topics_progress.keys())}"
                ),
                secondary_queries=[
                    "subsection synthesis cross-topic relationships business entities metrics joins",
                ],
                per_query_k=10,
                max_docs=24,
            ),
        )

        content_obj.content_json = result
        content_obj.status = "generated"
        content_obj.save()

        return content_obj

    def collect_topics_progress(self, topics):
        """Collect the minimal topic progress needed for subsection synthesis."""

        topics_progress = {}

        for topic in topics:
            if not hasattr(topic, "content") or not topic.content.content_json:
                continue

            element_progress = topic.content.content_json.get(
                "element_progress",
                {},
            )

            if element_progress:
                topics_progress[topic.title] = element_progress

        return topics_progress

    def validate_section_generation(self, section):
        """Validate section content generation prerequisites."""

        subsections = list(section.sub_sections.order_by("created_at"))

        if not subsections:
            raise ValueError(
                "Subsections are required before generating section content."
            )

        incomplete_subsections = [
            subsection.title
            for subsection in subsections
            if not hasattr(subsection, "content")
            or subsection.content.status != "generated"
        ]

        if incomplete_subsections:
            raise ValueError(
                "All subsection content must be generated first. Missing: "
                + ", ".join(incomplete_subsections)
            )

        return subsections

    def get_section_content(self, section):
        """Get section content."""

        content_obj, _ = SectionContent.objects.get_or_create(
            section=section,
            defaults={
                "content_json": {},
                "status": "draft",
            },
        )

        return content_obj

    def generate_section_content(
        self,
        project,
        report,
        section,
        subsections,
        content_obj,
    ):
        """Generate section-level synthesized content."""

        content_obj.status = "in_progress"
        content_obj.save()

        subsections_themes = self.collect_subsections_themes(subsections)

        result = generate_section_content(
            project=project,
            project_id=project.id,
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            report_title=report.title,
            section_title=section.title,
            subsections_themes=subsections_themes,
            metadata_context=retrieve_multi_table_metadata(
                project=project,
                primary_query=(
                    f"{report.title} {section.title} {' '.join(subsections_themes.keys())}"
                ),
                secondary_queries=[
                    "section synthesis cross-subsection relationships business entities measures joins",
                ],
                per_query_k=10,
                max_docs=24,
            ),
        )

        content_obj.content_json = result
        content_obj.status = "generated"
        content_obj.save()

        return content_obj

    def collect_subsections_themes(self, subsections):
        """Collect subsection themes for section synthesis."""

        subsections_themes = {}

        for subsection in subsections:
            if not hasattr(subsection, "content") or not subsection.content.content_json:
                continue

            key_themes = subsection.content.content_json.get("key_themes", [])

            if key_themes:
                subsections_themes[subsection.title] = key_themes

        return subsections_themes

    def repair_topic_content(self, project, report, topic, content_obj):
        """Repair topic content after visual placeholder failures."""

        repaired_content = repair_topic_content(
            project=project,
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            section_title=topic.subsection.section.title,
            subsection_title=topic.subsection.title,
            topic_title=topic.title,
            topic_plan=topic.analysis_plan.plan_json,
            content_json=content_obj.content_json or {},
        )

        content_obj.content_json = repaired_content
        content_obj.save()

        return content_obj

    def delete_topic_with_dependencies(self, topic):
        """Delete a failed topic and all dependent records via cascade."""

        topic.delete()

    def generate_report_document(self, report, progress_callback=None):

        approved_topics = Prefetch(
            "topics",
            queryset=Topic.objects.filter(is_approved=True)
            .select_related("content")
            .order_by("created_at"),
        )

        sections = (
            Section.objects.filter(report=report)
            .select_related("content")
            .prefetch_related(
                Prefetch(
                    "sub_sections",
                    queryset=SubSection.objects.select_related("content")
                    .prefetch_related(approved_topics)
                    .order_by("created_at"),
                ),
            )
            .order_by("created_at")
        )

        document_buffer = generate_report_document(
            report,
            sections,
            progress_callback=progress_callback,
        )

        filename = f"{slugify(report.title)}_report.docx"

        return document_buffer, filename
