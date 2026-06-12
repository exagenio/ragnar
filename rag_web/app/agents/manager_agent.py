from concurrent.futures import ThreadPoolExecutor
import threading
import time
import traceback

from django.conf import settings
from django.utils.timezone import now

from app.agents.content_agent import ContentAgent
from app.agents.metadata_agent import MetadataAgent
from app.agents.visual_Agent import VisualAgent
from app.models import (
    SubSectionGenerateTime,
    TopicGenerateTime,
)
from app.services.project_service import ProjectService
from app.services.task_tracker import (
    complete_background_task,
    create_background_task,
    fail_background_task,
    log_background_task,
    start_background_task,
)
from app.services.topic_gen.visual_gen.visual_narrative_generator import repair_content_chunk
from app.utils.block_processing import (
    apply_repaired_blocks,
    build_block_chunks,
    build_prompt_blocks,
)
from app.utils.data_decoder import decode_sql_result
from app.utils.visual_utils import has_pending_visuals

try:
    from google.api_core.exceptions import ResourceExhausted
except Exception:  # pragma: no cover - optional runtime import
    ResourceExhausted = None


class ManagerAgent:
    """Central orchestrator of the system."""

    def __init__(self):
        self.project_service = ProjectService()
        self.metadata_agent = MetadataAgent()
        self.content_agent = ContentAgent()
        self.visual_agent = VisualAgent()

    def create_project_with_database(self, data):
        self.project_service.test_db_connection(data)
        project = self.project_service.create_project_with_db(data)
        return project

    def update_project_llm_settings(self, project, data):
        return self.project_service.update_project_llm_settings(project, data)

    def discover_tables(self, db_connection):
        return self.metadata_agent.discover_tables(db_connection)

    def save_selected_tables(self, project, tables):
        return self.metadata_agent.save_selected_tables(project, tables)

    def get_schema_info(self, project):
        return self.metadata_agent.get_schema_info(project)

    def sample_table_rows(self, project, limit=10):
        return self.metadata_agent.sample_rows(project, limit)

    def start_metadata_generation(self, project):
        return self.metadata_agent.start_metadata_generation(project)

    def approve_table_metadata(
        self,
        metadata_obj,
        table_description,
        columns,
        confidence_notes,
    ):
        return self.metadata_agent.approve_metadata(
            metadata_obj,
            table_description,
            columns,
            confidence_notes,
        )

    def start_report(self, project, data):
        return self.content_agent.start_report(project, data)

    def update_outline(self, outline_obj, updated_outline):
        return self.content_agent.update_outline(outline_obj, updated_outline)

    def approve_outline(self, report):
        return self.content_agent.approve_outline(report)

    def generate_topics(self, report, subsection, section, project_id):
        return self.content_agent.generate_topics(
            report,
            subsection,
            section,
            project_id,
        )

    def save_topics(self, report, subsection, submitted_titles):
        return self.content_agent.save_topics(report, subsection, submitted_titles)

    def approve_topics(self, subsection, section):
        return self.content_agent.approve_topics(subsection, section)

    def generate_topic_analysis_plan(self, project, report, topic):
        return self.content_agent.generate_topic_analysis_plan(project, report, topic)

    def update_topic_analysis_plan(self, plan_obj, topic, form_data, approve=False):
        plan = self.content_agent.update_topic_analysis_plan(
            plan_obj,
            topic,
            form_data,
            approve,
        )
        plan_obj.save()

    def generate_topic_content(self, project, report, topic, content_obj):
        return self._run_topic_pipeline(
            project=project,
            report=report,
            topic=topic,
            plan_generated=True,
        )

    def compute_visual_block(self, project, report, topic, content_obj, section_index, block_index):
        result = self.visual_agent.compute_visual_block(
            project,
            topic,
            content_obj,
            section_index,
            block_index,
        )

        if isinstance(result, dict) and result.get("placeholder_removed") and not result.get("success"):
            print(f"[REPAIR] Visual placeholder removed -> Topic {topic.id}")
            content_obj = self.content_agent.repair_topic_content(
                project,
                report,
                topic,
                content_obj,
            )

        return result

    def validate_subsection_generation(self, subsection):
        return self.content_agent.validate_subsection_generation(subsection)

    def get_subsection_content(self, subsection):
        return self.content_agent.get_subsection_content(subsection)

    def generate_subsection_content(self, project, report, subsection, topics, content_obj):
        return self.content_agent.generate_subsection_content(
            project,
            report,
            subsection,
            topics,
            content_obj,
        )

    def validate_section_generation(self, section):
        return self.content_agent.validate_section_generation(section)

    def get_section_content(self, section):
        return self.content_agent.get_section_content(section)

    def generate_section_content(self, project, report, section, subsections, content_obj):
        return self.content_agent.generate_section_content(
            project,
            report,
            section,
            subsections,
            content_obj,
        )

    def generate_report_document(self, report):
        return self.content_agent.generate_report_document(report)

    def _emit_task_log(self, task_id, message, level="info"):
        print(message)
        if task_id:
            log_background_task(task_id, message, level=level)

    def trigger_subsection_auto_generation(self, project, report, subsection):
        if subsection.is_generating:
            print("[AUTO] Subsection already generating")
            return None

        subsection.is_generating = True
        subsection.save()

        task = create_background_task(
            task_type="subsection_pipeline",
            title=f"Subsection pipeline for {subsection.title}",
            description="Generate topics, run topic pipelines, and compose subsection content.",
            project=project,
            report=report,
            subsection=subsection,
        )

        self._emit_task_log(
            task.id,
            f"[AUTO] Triggered auto generation for subsection '{subsection.title}'.",
        )

        thread = threading.Thread(
            target=self._run_subsection_pipeline,
            args=(project, report, subsection, task.id),
            daemon=True,
        )
        thread.start()
        return task

    def delete_topic_with_dependencies(self, topic):
        return self.content_agent.delete_topic_with_dependencies(topic)

    def _is_retryable_llm_error(self, exc):
        if ResourceExhausted and isinstance(exc, ResourceExhausted):
            return True

        message = str(exc).lower()
        retry_markers = [
            "resource exhausted",
            "429",
            "rate limit",
            "quota",
            "too many requests",
        ]
        return any(marker in message for marker in retry_markers)

    def _topic_pipeline_workers_for_project(self, project):
        configured_workers = getattr(settings, "TOPIC_PIPELINE_WORKERS", 2)
        return max(2, min(int(configured_workers), 3))

    def _visual_pipeline_workers_for_project(self, project):
        configured_workers = getattr(settings, "VISUAL_PIPELINE_WORKERS", 1)
        return max(1, min(int(configured_workers), 2))

    def _run_topic_pipeline_with_retry(
        self,
        project,
        report,
        topic,
        task_id=None,
        plan_generated=False,
        max_attempts=2,
    ):
        last_error = None
        if task_id:
            start_background_task(task_id, f"Topic pipeline started for '{topic.title}'.")

        for attempt in range(1, max_attempts + 1):
            try:
                self._execute_topic_pipeline_once(
                    project,
                    report,
                    topic,
                    task_id=task_id,
                    plan_generated=plan_generated,
                )
                if task_id:
                    complete_background_task(
                        task_id,
                        f"Topic pipeline completed for '{topic.title}'.",
                    )
                return {
                    "success": True,
                    "topic_id": topic.id,
                    "topic_title": topic.title,
                }
            except Exception as exc:
                last_error = exc
                self._emit_task_log(
                    task_id,
                    f"[TOPIC RETRY] Topic {topic.id} attempt {attempt}/{max_attempts} failed: {exc}",
                    level="warning",
                )

                if attempt < max_attempts and self._is_retryable_llm_error(exc):
                    backoff_seconds = 8 * attempt
                    self._emit_task_log(
                        task_id,
                        f"[TOPIC RETRY] Waiting {backoff_seconds}s before retrying topic {topic.id}.",
                    )
                    time.sleep(backoff_seconds)
                    continue

                if attempt < max_attempts:
                    self._emit_task_log(
                        task_id,
                        f"[TOPIC RETRY] Retrying topic {topic.id} once more after failure.",
                    )
                    time.sleep(2)

        topic_id = topic.id
        topic_title = topic.title
        self.delete_topic_with_dependencies(topic)

        self._emit_task_log(
            task_id,
            f"[TOPIC CLEANUP] Removed failed topic {topic_id} ({topic_title}) after {max_attempts} attempts.",
            level="error",
        )

        if task_id:
            fail_background_task(
                task_id,
                str(last_error) if last_error else "Unknown topic pipeline error",
            )

        return {
            "success": False,
            "topic_id": topic_id,
            "topic_title": topic_title,
            "error": str(last_error) if last_error else "Unknown topic pipeline error",
        }

    def _run_subsection_pipeline(self, project, report, subsection, task_id=None):
        start_time = now()
        status = "success"
        error_message = ""
        try:
            if task_id:
                start_background_task(
                    task_id,
                    f"Subsection pipeline started for '{subsection.title}'.",
                )

            section = subsection.section
            self._emit_task_log(
                task_id,
                f"[AUTO] Starting subsection pipeline for subsection {subsection.id}.",
            )

            self.generate_topics(report, subsection, section, project.id)
            topics = list(subsection.topics.all())
            self._emit_task_log(
                task_id,
                f"[AUTO] Generated {len(topics)} topic candidate(s).",
            )

            self.approve_topics(subsection, section)
            self._emit_task_log(task_id, "[AUTO] Topics approved.")

            successful_topics = []
            failed_topics = []
            topic_workers = self._topic_pipeline_workers_for_project(project)
            self._emit_task_log(
                task_id,
                f"[AUTO] Running up to {topic_workers} topic pipelines concurrently.",
            )

            with ThreadPoolExecutor(
                max_workers=topic_workers
            ) as executor:
                futures = []

                for topic in topics:
                    topic_task = create_background_task(
                        task_type="topic_pipeline",
                        title=f"Topic pipeline for {topic.title}",
                        description="Generate a topic plan and create vector-grounded content.",
                        project=project,
                        report=report,
                        subsection=subsection,
                        topic=topic,
                        parent_id=task_id,
                    )
                    futures.append(
                        executor.submit(
                            self._run_topic_pipeline_with_retry,
                            project,
                            report,
                            topic,
                            topic_task.id,
                        )
                    )

                for future in futures:
                    try:
                        result = future.result()
                        if result and result.get("success"):
                            successful_topics.append(result)
                        elif result:
                            failed_topics.append(result)
                    except Exception as exc:
                        self._emit_task_log(
                            task_id,
                            f"[AUTO] Topic pipeline failed: {exc}",
                            level="error",
                        )

            self._emit_task_log(task_id, "[AUTO] All topic pipelines completed.")

            if failed_topics:
                failed_titles = ", ".join(item["topic_title"] for item in failed_topics)
                self._emit_task_log(
                    task_id,
                    f"[AUTO] Failed topics were removed after retry exhaustion: {failed_titles}",
                    level="warning",
                )

            if not successful_topics:
                status = "failed"
                error_message = (
                    "All topic pipelines failed. Failed topics were removed; "
                    "subsection content generation was skipped."
                )
                self._emit_task_log(task_id, f"[AUTO] {error_message}", level="error")
                return

            topics = self.validate_subsection_generation(subsection)
            subsection_content = self.get_subsection_content(subsection)
            self.generate_subsection_content(
                project,
                report,
                subsection,
                topics,
                subsection_content,
            )

            self._emit_task_log(
                task_id,
                "[AUTO] Subsection content generated.",
                level="success",
            )
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            self._emit_task_log(
                task_id,
                f"[AUTO ERROR] Subsection {subsection.id}: {exc}",
                level="error",
            )
            traceback.print_exc()
        finally:
            end_time = now()
            SubSectionGenerateTime.objects.create(
                subsection=subsection,
                report=report,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                topics_count=len(subsection.topics.all()),
                status=status,
                error_message=error_message,
            )
            subsection.is_generating = False
            subsection.save()

            if task_id:
                if status == "success":
                    complete_background_task(
                        task_id,
                        f"Subsection pipeline completed for '{subsection.title}'.",
                    )
                else:
                    fail_background_task(
                        task_id,
                        error_message or f"Subsection pipeline failed for '{subsection.title}'.",
                    )

            print(f"[AUTO] Subsection pipeline finished -> Subsection {subsection.id}")

    def _run_topic_pipeline(self, project, report, topic, plan_generated=False):
        try:
            return self._execute_topic_pipeline_once(
                project,
                report,
                topic,
                plan_generated=plan_generated,
            )
        except Exception as exc:
            print(f"[PIPELINE ERROR] Topic {topic.id}: {exc}")
            traceback.print_exc()
            return None

    def _execute_topic_pipeline_once(self, project, report, topic, task_id=None, plan_generated=False):
        start_time = now()
        status = "success"
        error_message = ""
        try:
            self._emit_task_log(task_id, f"[PIPELINE] Start -> Topic {topic.id}")

            content_obj = self._stage_analysis_and_sql(
                project,
                report,
                topic,
                task_id=task_id,
                plan_generated=plan_generated,
            )
            content_obj = self._stage_generate_content(
                project,
                report,
                topic,
                content_obj,
                task_id=task_id,
            )
            content_obj = self._stage_generate_visuals(
                project,
                report,
                topic,
                content_obj,
                task_id=task_id,
            )
            content_obj = self._stage_repair_visual_narrative(
                project,
                report,
                topic,
                content_obj,
                task_id=task_id,
            )

            self._emit_task_log(task_id, f"[PIPELINE] Completed -> Topic {topic.id}", level="success")
            return content_obj
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            self._emit_task_log(task_id, f"[PIPELINE ERROR] Topic {topic.id}: {exc}", level="error")
            traceback.print_exc()
            raise
        finally:
            end_time = now()
            TopicGenerateTime.objects.create(
                topic=topic,
                subsection=topic.subsection,
                report=report,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                status=status,
                error_message=error_message,
            )

    def _stage_analysis_and_sql(self, project, report, topic, task_id=None, plan_generated=False):
        if not plan_generated:
            plan_obj = self.generate_topic_analysis_plan(project, report, topic)
            plan_obj.is_approved = True
            topic.is_approved = True
            topic.save()
            plan_obj.save()
        else:
            self.content_agent.get_topic_content(topic)

        content_obj = self.content_agent.get_topic_content(topic)
        self._emit_task_log(task_id, f"[STAGE 1] Analysis plan ready -> Topic {topic.id}")
        return content_obj

    def _stage_generate_content(self, project, report, topic, content_obj, task_id=None):
        content_obj = self.content_agent.generate_topic_content(
            project,
            report,
            topic,
            content_obj,
        )
        self._emit_task_log(task_id, f"[STAGE 2] Content generated -> Topic {topic.id}")
        return content_obj

    def _stage_generate_visuals(self, project, report, topic, content_obj, task_id=None):
        max_rounds = 3

        for attempt in range(max_rounds):
            self._emit_task_log(task_id, f"[STAGE 3] Round {attempt + 1} -> Topic {topic.id}")
            sections = content_obj.content_json.get("sections", [])
            tasks = []

            with ThreadPoolExecutor(
                max_workers=self._visual_pipeline_workers_for_project(project)
            ) as executor:
                for section_index, section in enumerate(sections):
                    blocks = section.get("content_blocks", [])
                    for block_index, block in enumerate(blocks):
                        if block.get("type") != "visual_placeholder":
                            continue
                        if block.get("generated_visual"):
                            continue

                        tasks.append(
                            executor.submit(
                                self._process_visual_block_pipeline,
                                project,
                                report,
                                topic,
                                content_obj,
                                section_index,
                                block_index,
                            )
                        )

                for task in tasks:
                    try:
                        task.result()
                    except Exception as exc:
                        self._emit_task_log(task_id, f"[VISUAL ERROR] {exc}", level="warning")

            if not has_pending_visuals(content_obj):
                self._emit_task_log(task_id, f"[STAGE 3] All visuals done -> Topic {topic.id}")
                break

        return content_obj

    def _process_visual_block_pipeline(
        self,
        project,
        report,
        topic,
        content_obj,
        section_index,
        block_index,
    ):
        self.compute_visual_block(
            project,
            report,
            topic,
            content_obj,
            section_index,
            block_index,
        )

    def _inject_visual_with_narrative(
        self,
        content_obj,
        section_index,
        block_index,
        narrative,
        visual_block,
    ):
        sections = content_obj.content_json["sections"]
        blocks = sections[section_index]["content_blocks"]

        before = narrative.get("before_block")
        after = narrative.get("after_block")

        new_blocks = []
        if before:
            new_blocks.append(before)
        new_blocks.append(visual_block)
        if after:
            new_blocks.append(after)

        blocks[block_index:block_index + 1] = new_blocks
        content_obj.save()

    def _has_pending_visuals(self, content_obj):
        for section in content_obj.content_json.get("sections", []):
            for block in section.get("content_blocks", []):
                if block.get("type") == "visual_placeholder" and not block.get("generated_visual"):
                    return True
        return False

    def _stage_repair_visual_narrative(self, project, report, topic, content_obj, task_id=None):
        self._emit_task_log(task_id, f"[STAGE 4] Block-level repair -> Topic {topic.id}")

        sections = content_obj.content_json.get("sections", [])
        for section in sections:
            blocks = section.get("content_blocks", [])
            formatted_blocks = build_prompt_blocks(blocks, decode_sql_result)
            chunks = build_block_chunks(formatted_blocks, chunk_size=6)
            all_updates = []

            for chunk in chunks:
                try:
                    updates = repair_content_chunk(
                        project=project,
                        blocks_chunk=chunk,
                    )
                    all_updates.extend(updates)
                except Exception as exc:
                    self._emit_task_log(
                        task_id,
                        f"[REPAIR ERROR] Topic {topic.id}: {exc}",
                        level="warning",
                    )
                    traceback.print_exc()

            section["content_blocks"] = apply_repaired_blocks(blocks, all_updates)

        content_obj.save()
        self._emit_task_log(task_id, f"[STAGE 4] Completed -> Topic {topic.id}")
        return content_obj

    def normalize_visual_block(self, block):
        raw = block.get("content")
        if isinstance(raw, dict):
            return block

        if isinstance(raw, str) and "{{VISUAL" in raw:
            import re

            def extract(field):
                match = re.search(rf"{field}\s*:\s*(.*?);", raw, re.DOTALL)
                return match.group(1).strip().strip('"') if match else ""

            block["content"] = {
                "id": extract("id"),
                "type": extract("type"),
                "purpose": extract("purpose"),
            }

        return block
