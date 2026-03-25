# content agent
from app.models import Report, ReportOutline
from app.services.report_outline_generator import generate_report_outline
from app.models import Section, SubSection
from app.models import Topic, SelectedTable
from app.services.subsection_topic_generator import generate_subsection_topics
from app.services.column_introspector import get_table_columns
from app.models import TopicAnalysisPlan
from app.services.topic_analysis_plan_generator import generate_topic_analysis_plan
from app.services.topic_content_generator import generate_topic_content
from app.models import SubSectionContent
from app.services.sub_section_content_generator import generate_subsection_content
from app.models import SectionContent
from app.services.section_content_generator import generate_section_content
from django.utils.text import slugify
from app.models import Section, TopicContent
from app.services.document_generator import generate_report_document
import json
from app.services.placeholder_normalizer import normalize_placeholders
from app.services.topic_content_repair import repair_topic_content

class ContentAgent:

    def start_report(self, project, data):
        """
        Creates a new report and generates its outline.
        """

        outline = generate_report_outline(data)

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

        outline_obj.outline_json = updated_outline
        outline_obj.save()

        return outline_obj


    def approve_outline(self, report):

        outline_obj = report.outline
        outline_obj.approved = True
        outline_obj.save()

        report.status = "outline_approved"
        report.outline_approved = True
        report.save()

        outline_data = outline_obj.outline_json

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
            project_id=project_id,
        )

        for topic_title in result.get("topics", []):
            Topic.objects.create(
                subsection=subsection,
                report=report,
                title=topic_title,
            )

    def save_topics(self, report, subsection, submitted_titles):

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

        Topic.objects.filter(subsection=subsection).update(is_approved=True)

        subsection.is_topics_approved = True
        subsection.save()

        section.is_sub_sec_appvroved = True
        section.save()

    def build_schema_context(self, project):

        tables = SelectedTable.objects.filter(project=project)

        schema_context = []

        for t in tables:
            columns = get_table_columns(project.db_connection, t.table_name)

            schema_context.append(
                {
                    "table": t.table_name,
                    "columns": [
                        {"name": col["name"], "type": col["type"]}
                        for col in columns
                    ],
                }
            )

        return schema_context
    
    def generate_topic_analysis_plan(self, project, report, topic):

        subsection = topic.subsection
        section = subsection.section

        schema_context = self.build_schema_context(project)

        plan_obj, created = TopicAnalysisPlan.objects.get_or_create(
            report=report,
            topic=topic,
            defaults={"plan_json": {}},
        )

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

            plan = generate_topic_analysis_plan(context)

            plan_obj.plan_json = plan
            plan_obj.save()

        return plan_obj
    
    def update_topic_analysis_plan(self, plan_obj, topic, form_data, approve=False):

        plan = plan_obj.plan_json.copy()

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

        content_obj.status = "in_progress"
        content_obj.save()

        precomputed = (content_obj.content_json or {}).get(
            "precomputed_sql_placeholders", []
        )

        result = generate_topic_content(
            project_id=project.id,
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            section_title=topic.subsection.section.title,
            subsection_title=topic.subsection.title,
            topic_title=topic.title,
            topic_plan=topic.analysis_plan.plan_json,
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

        content_obj, _ = SubSectionContent.objects.get_or_create(
            subsection=subsection,
            defaults={
                "content_json": {},
                "status": "draft",
            },
        )

        return content_obj


    def validate_subsection_generation(self, subsection):

        topics = subsection.topics.filter(is_approved=True)

        if not topics.exists():
            raise ValueError("No approved topics found for this subsection.")

        all_topics_have_content = all(
            hasattr(topic, "content") and topic.content.status == "generated"
            for topic in topics
        )

        if not all_topics_have_content:
            raise ValueError(
                "All topics must have generated content before creating subsection content."
            )

        return topics


    def collect_topics_progress(self, topics):

        topics_progress = {}

        for topic in topics:
            if hasattr(topic, "content") and topic.content.content_json:

                element_progress = topic.content.content_json.get(
                    "element_progress",
                    {},
                )

                topics_progress[topic.title] = element_progress

        return topics_progress


    def generate_subsection_content(
        self,
        project,
        report,
        subsection,
        topics,
        content_obj,
    ):

        content_obj.status = "in_progress"
        content_obj.save()

        topics_progress = self.collect_topics_progress(topics)

        result = generate_subsection_content(
            project_id=project.id,
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            report_title=report.title,
            section_title=subsection.section.title,
            subsection_title=subsection.title,
            topics_progress=topics_progress,
        )

        content_obj.content_json = result
        content_obj.status = "generated"
        content_obj.save()

        return content_obj
    
    def validate_section_generation(self, section):

        subsections = section.sub_sections.all()

        if not subsections.exists():
            raise ValueError("No subsections found for this section.")

        all_have_content = all(
            hasattr(subsection, "content") and subsection.content.status == "generated"
            for subsection in subsections
        )

        if not all_have_content:
            raise ValueError(
                "All subsections must have generated content before creating section content."
            )

        return subsections


    def get_section_content(self, section):

        content_obj, _ = SectionContent.objects.get_or_create(
            section=section,
            defaults={
                "content_json": {},
                "status": "draft",
            },
        )

        return content_obj


    def collect_subsections_themes(self, subsections):

        subsections_themes = {}

        for subsection in subsections:
            if hasattr(subsection, "content") and subsection.content.content_json:

                key_themes = subsection.content.content_json.get(
                    "key_themes",
                    [],
                )

                subsections_themes[subsection.title] = key_themes

        return subsections_themes


    def generate_section_content(
        self,
        project,
        report,
        section,
        subsections,
        content_obj,
    ):

        content_obj.status = "in_progress"
        content_obj.save()

        subsections_themes = self.collect_subsections_themes(subsections)

        result = generate_section_content(
            project_id=project.id,
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            report_title=report.title,
            section_title=section.title,
            subsections_themes=subsections_themes,
        )

        content_obj.content_json = result
        content_obj.status = "generated"
        content_obj.save()

        return content_obj

    
    def generate_report_document(self, report):

        sections = (
            Section.objects.filter(report=report)
            .prefetch_related(
                "sub_sections__topics__content",
                "sub_sections__content",
                "content",
            )
            .order_by("created_at")
        )

        document_buffer = generate_report_document(report, sections)

        filename = f"{slugify(report.title)}_report.docx"

        return document_buffer, filename
    
    def repair_topic_content(
    self,
    project,
    report,
    topic,
    content_obj,
    ):
        content_json = content_obj.content_json

        repaired = repair_topic_content(
            industry=report.industry,
            report_type=report.report_type,
            audience=report.audience,
            purpose=report.purpose,
            section_title=topic.subsection.section.title,
            subsection_title=topic.subsection.title,
            topic_title=topic.title,
            topic_plan=topic.analysis_plan.plan_json,
            content_json=content_json,
        )

        content_obj.content_json = repaired
        content_obj.save()

        return content_obj