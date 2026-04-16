from app.services.project_service import ProjectService
from app.agents.metadata_agent import MetadataAgent
from app.agents.content_agent import ContentAgent
from app.agents.sql_agent import SQLAgent
from app.agents.visual_Agent import VisualAgent
import threading
from concurrent.futures import ThreadPoolExecutor
from app.models import Topic
from app.models import Section, TopicContent, TopicAnalysisPlan, SubSectionGenerateTime, TopicGenerateTime
from rag_web.app.services.vector_db_config.vector_store import get_vector_store
import base64
import struct
from rag_web.app.services.topic_gen.visual_gen.visual_narrative_generator import repair_content_chunk
import traceback
from django.utils.timezone import now
class ManagerAgent:
    """
    Central orchestrator of the system.

    Django Views communicate ONLY with this agent.
    The ManagerAgent coordinates all other agents.
    """

    def __init__(self):
        self.project_service = ProjectService()
        self.metadata_agent = MetadataAgent()
        self.content_agent = ContentAgent()
        self.sql_agent = SQLAgent()
        self.visual_agent = VisualAgent()

    def create_project_with_database(self, data):
        """
        Orchestrates project creation workflow.
        """

        # 1. Validate DB connection
        self.project_service.test_db_connection(data)

        # 2. Create project and DB connection
        project = self.project_service.create_project_with_db(data)

        return project


    # ----------------------------
    # Metadata operations
    # ----------------------------

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
            report, subsection, section, project_id
        )


    def save_topics(self, report, subsection, submitted_titles):
        return self.content_agent.save_topics(
            report, subsection, submitted_titles
        )


    def approve_topics(self, subsection, section):
        return self.content_agent.approve_topics(subsection, section)
    
    def generate_topic_analysis_plan(self, project, report, topic):
        return self.content_agent.generate_topic_analysis_plan(
            project,
            report,
            topic,
        )


    def update_topic_analysis_plan(self, plan_obj, topic, form_data, approve=False):
        plan = self.content_agent.update_topic_analysis_plan(
            plan_obj,
            topic,
            form_data,
            approve,
        )
        if approve :
             self.generate_precomputed_sql_placeholders(topic, plan)
        plan_obj.save()

    
    def generate_topic_content(self, project, report, topic, content_obj):
        return self._run_topic_pipeline(project=project, report=report, topic=topic, plan_generated=True)

    def compute_visual_block(self, project, report, topic, content_obj, section_index, block_index):
        result = self.visual_agent.compute_visual_block(
            project,
            topic,
            content_obj,
            section_index,
            block_index,
        )

        if isinstance(result, dict) and result.get("placeholder_removed") and not result.get("success"):

            print(f"[REPAIR] Visual placeholder removed → Topic {topic.id}")

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
    


    def trigger_subsection_auto_generation(self, project, report, subsection):

        if subsection.is_generating:
            print("[AUTO] Subsection already generating")
            return False

        subsection.is_generating = True
        subsection.save()

        print(f"[AUTO] Triggered auto generation → Subsection {subsection.id}")

        thread = threading.Thread(
            target=self._run_subsection_pipeline,
            args=(project, report, subsection),
            daemon=True,
        )

        thread.start()

        return True


    # ---------------------------------------
    # MAIN PIPELINE
    # ---------------------------------------

    def _run_subsection_pipeline(self, project, report, subsection):
        start_time = now()
        status = "success"
        error_message = ""
        try:

            section = subsection.section

            print(f"[AUTO] Starting subsection pipeline → Subsection {subsection.id}")

            # -----------------------------
            # Generate Topics
            # -----------------------------
            self.generate_topics(report, subsection, section, project.id)

            topics = list(subsection.topics.all())

            print(f"[AUTO] Generated {len(topics)} topics")

            # -----------------------------
            # Approve Topics
            # -----------------------------
            self.approve_topics(subsection, section)

            print("[AUTO] Topics approved")

            # -----------------------------
            # Concurrent Topic Pipelines
            # -----------------------------
            with ThreadPoolExecutor(max_workers=3) as executor:

                futures = []

                for topic in topics:

                    futures.append(
                        executor.submit(
                            self._run_topic_pipeline,
                            project,
                            report,
                            topic,
                        )
                    )

                for f in futures:
                    try:
                        f.result()
                    except Exception as e:
                        print(f"[AUTO] Topic pipeline failed: {e}")

            print("[AUTO] All topic pipelines completed")

            # -----------------------------
            # Generate Subsection Content
            # -----------------------------
            topics = self.validate_subsection_generation(subsection)

            subsection_content = self.get_subsection_content(subsection)

            self.generate_subsection_content(
                project,
                report,
                subsection,
                topics,
                subsection_content,
            )

            print("[AUTO] Subsection content generated")

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

            print(f"[AUTO] Subsection pipeline finished → Subsection {subsection.id}")

    # ---------------------------------------
    # SINGLE TOPIC PIPELINE
    # ---------------------------------------

    def _run_topic_pipeline(self, project, report, topic, plan_generated=False):
        start_time = now()
        status = "success"
        error_message = ""
        try:
            print(f"[PIPELINE] Start → Topic {topic.id}")

            # -----------------------------
            # 1. PLAN + SQL PLACEHOLDERS
            # -----------------------------
            content_obj = self._stage_analysis_and_sql(project, report, topic, plan_generated)

            # -----------------------------
            # 2. CONTENT GENERATION
            # -----------------------------

            content_obj = self._stage_generate_content(
                project, report, topic, content_obj
            )

            # -----------------------------
            # 3. VISUAL PIPELINE (NEW)
            # -----------------------------
            content_obj = self._stage_generate_visuals(
                project, report, topic, content_obj
            )

            content_obj = self._stage_repair_visual_narrative(
                project, report, topic, content_obj
            )

            print(f"[PIPELINE] Completed → Topic {topic.id}")
            return content_obj
        except Exception as e:
            print(f"[PIPELINE ERROR] Topic {topic.id}: {e}")
            traceback.print_exc()
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


    def _stage_analysis_and_sql(self, project, report, topic, plan_generated=False):
        if not plan_generated:
            plan_obj = self.generate_topic_analysis_plan(project, report, topic)

            plan_obj.is_approved = True
            topic.is_approved = True

            topic.save()
            plan_obj.save()
            content_obj = self.generate_precomputed_sql_placeholders(topic, plan_obj.plan_json)
        else:
            content_obj = self.content_agent.get_topic_content(topic)       
        content_obj = self.content_agent.get_topic_content(topic)
        content_obj = self.sql_agent.compute_precomputed_sql_placeholders(
            project=project,
            topic_content_obj=content_obj,
            topic=topic,
        )
        print(f"[STAGE 1] Analysis + SQL ready → Topic {topic.id}")
        return content_obj


    def _stage_generate_content(self, project, report, topic, content_obj):
        content_obj = self.content_agent.generate_topic_content(
            project,
            report,
            topic,
            content_obj,
        )

        print(f"[STAGE 2] Content generated → Topic {topic.id}")

        return content_obj
    

    def _stage_generate_visuals(self, project, report, topic, content_obj):

        MAX_ROUNDS = 3

        for attempt in range(MAX_ROUNDS):

            print(f"[STAGE 3] Round {attempt+1} → Topic {topic.id}")

            sections = content_obj.content_json.get("sections", [])

            tasks = []

            with ThreadPoolExecutor(max_workers=3) as executor:

                for s_index, section in enumerate(sections):

                    blocks = section.get("content_blocks", [])

                    for b_index, block in enumerate(blocks):

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
                                s_index,
                                b_index,
                            )
                        )

                for t in tasks:
                    try:
                        t.result()
                    except Exception as e:
                        print(f"[VISUAL ERROR] {e}")

            # -----------------------------
            # CHECK REMAINING
            # -----------------------------
            if not self._has_pending_visuals(content_obj):
                print(f"[STAGE 3] All visuals done → Topic {topic.id}")
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

        # -------------------------
        # 1. GENERATE VISUAL
        # -------------------------
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

        # replace placeholder with:
        # before → visual → after

        new_blocks = []

        if before:
            new_blocks.append(before)

        new_blocks.append(visual_block)

        if after:
            new_blocks.append(after)

        # replace original placeholder
        blocks[block_index:block_index+1] = new_blocks

        content_obj.save()

    def _has_pending_visuals(self, content_obj):

        for section in content_obj.content_json.get("sections", []):
            for block in section.get("content_blocks", []):
                if block.get("type") == "visual_placeholder" and not block.get("generated_visual"):
                    return True

        return False

    def generate_precomputed_sql_placeholders(self, topic, plan):
        
        content_obj, _ = TopicContent.objects.get_or_create(
            topic=topic,
            defaults={
                "content_json": {},
                "status": "draft",
                "iteration_count": 0,
            },
        )

        # -----------------------------
        # 1. METADATA CONTEXT
        # -----------------------------
        vector_store = get_vector_store()

        metadata_context = vector_store.similarity_search(
            f"{topic.title} {plan.get('required_elements', [])}",
            k=8,
            filter={"project_id": topic.report.project.id},
        )

        metadata_context = [
            {"content": d.page_content, "metadata": d.metadata}
            for d in metadata_context
        ]

        # -----------------------------
        # 2. GENERATE PLACEHOLDERS
        # -----------------------------
        sql_agent = SQLAgent()

        placeholders_result = sql_agent.generate_sql_placeholders_from_plan(
            topic_plan=plan,
            project=topic.report.project,
            metadata_context=metadata_context,
        )

        placeholders = placeholders_result.get("placeholders", [])

        # -----------------------------
        # 3. FORMAT
        # -----------------------------
        def to_sql_block(p, topic_id, index):
            return {
                "type": "sql_placeholder",
                "content": {
                    "id": f"{topic_id}_{index}",
                    "calculation": p["calculation"],
                    "description": p["description"],
                    "data_requirement_ref": p["data_requirement_ref"],
                }
            }

        sql_blocks = [
            to_sql_block(p, topic.id, i)
            for i, p in enumerate(placeholders)
        ]

        # -----------------------------
        # 4. SAVE
        # -----------------------------
        content_json = content_obj.content_json or {}
        content_json["precomputed_sql_placeholders"] = sql_blocks

        content_obj.content_json = content_json
        content_obj.save()

        return content_obj

    def _stage_repair_visual_narrative(self, project, report, topic, content_obj):

        print(f"[STAGE 4] Block-level repair → Topic {topic.id}")

        sections = content_obj.content_json.get("sections", [])

        for section in sections:

            blocks = section.get("content_blocks", [])

            # 1. Extract
            formatted_blocks = self.build_prompt_blocks(blocks, self._decode_sql_result)

            # 2. Chunk
            chunks = self.build_block_chunks(formatted_blocks, chunk_size=6)

            all_updates = []

            for chunk in chunks:
                try:
                    updates = repair_content_chunk(
                        blocks_chunk=chunk,
                    )
                    all_updates.extend(updates)
                except Exception as e:
                    print(f"[REPAIR ERROR] Topic {topic.id}")
                    print(f"Error: {str(e)}")
                    traceback.print_exc()
            # 3. Apply
            section["content_blocks"] = self.apply_repaired_blocks(
                blocks,
                all_updates
            )

        content_obj.save()

        print(f"[STAGE 4] Completed → Topic {topic.id}")

        return content_obj


    def decode_bdata(self, bdata, dtype):
        binary = base64.b64decode(bdata)

        if dtype == "f8":
            return list(struct.unpack(f"{len(binary)//8}d", binary))
        elif dtype == "f4":
            return list(struct.unpack(f"{len(binary)//4}f", binary))
        elif dtype == "i4":
            return list(struct.unpack(f"{len(binary)//4}i", binary))
        elif dtype == "i2":
            return list(struct.unpack(f"{len(binary)//2}h", binary))
        elif dtype == "i1":
            return list(struct.unpack(f"{len(binary)}b", binary))

        return []
    
    def _decode_sql_result(self, sql_result):

        if not sql_result:
            return sql_result

        # table format
        if isinstance(sql_result, dict) and "rows" in sql_result:
            return sql_result

        # chart format
        if isinstance(sql_result, dict):

            decoded = {}

            for key, val in sql_result.items():

                if isinstance(val, dict) and "bdata" in val:
                    decoded[key] = self.decode_bdata(val["bdata"], val.get("dtype"))
                else:
                    decoded[key] = val

            return decoded

        return sql_result
    

    def build_prompt_blocks(self, blocks, decode_fn):

        formatted = []

        for i, block in enumerate(blocks):

            if block["type"] == "visual_placeholder":
                block = self.normalize_visual_block(block)

                content = block.get("content", {})

                decoded = decode_fn(
                    block.get("generated_visual", {}).get("data")
                )

                formatted.append({
                    "block_index": i,
                    "type": "visual",
                    "visual_id": content.get("id"),
                    "visual_type": content.get("type"),
                    "purpose": content.get("purpose"),
                    "data": decoded
                })

            elif block["type"] in ["paragraph", "bullet_list"]:

                formatted.append({
                    "block_index": i,
                    "type": block["type"],
                    "content": block["content"]
                })

        return formatted
    
    def build_block_chunks(self,blocks, chunk_size=8):
        """
        Chunk based on number of repairable blocks
        """
        chunks = []

        for i in range(0, len(blocks), chunk_size):
            chunks.append(blocks[i:i+chunk_size])

        return chunks
    
    def apply_repaired_blocks(self,original_blocks, repaired_blocks):

        for updated in repaired_blocks:

            idx = updated["block_index"]

            if idx >= len(original_blocks):
                continue

            if original_blocks[idx]["type"] not in ["paragraph", "bullet_list"]:
                continue

            original_blocks[idx]["content"] = updated["content"]

        return original_blocks
    
    def normalize_visual_block(self, block):
        raw = block.get("content")

        if isinstance(raw, dict):
            return block  # already correct

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