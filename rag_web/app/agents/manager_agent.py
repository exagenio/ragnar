from app.services.project_service import ProjectService
from app.agents.metadata_agent import MetadataAgent
from app.agents.content_agent import ContentAgent
from app.agents.sql_agent import SQLAgent
from app.agents.visual_Agent import VisualAgent
import threading
from concurrent.futures import ThreadPoolExecutor
from app.models import Topic

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
    
    def create_project_with_database(self, data):
        self.project_service.test_db_connection(data)
        return self.project_service.create_project_with_db(data)

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
        return self.content_agent.update_topic_analysis_plan(
            plan_obj,
            topic,
            form_data,
            approve,
        )
    
    def generate_topic_content(self, project, report, topic, content_obj):
        return self.content_agent.generate_topic_content(
            project,
            report,
            topic,
            content_obj,
        )
    
    def compute_sql_block(self, project, report, topic, content_obj, section_index, block_index):

        result = self.sql_agent.compute_sql_block(
            project,
            topic,
            content_obj,
            section_index,
            block_index,
        )

        if isinstance(result, dict) and result.get("placeholder_removed"):

            print(f"[REPAIR] SQL placeholder removed → Topic {topic.id}")

            content_obj = self.content_agent.repair_topic_content(
                project,
                report,
                topic,
                content_obj,
            )

        return result

    def compute_visual_block(self, project, report, topic, content_obj, section_index, block_index):
        result = self.visual_agent.compute_visual_block(
            project,
            topic,
            content_obj,
            section_index,
            block_index,
        )

        if isinstance(result, dict) and result.get("placeholder_removed"):

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
            with ThreadPoolExecutor(max_workers=5) as executor:

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

            subsection.is_generating = False
            subsection.save()

            print(f"[AUTO] Subsection pipeline finished → Subsection {subsection.id}")

    # ---------------------------------------
    # SINGLE TOPIC PIPELINE
    # ---------------------------------------

    def _run_topic_pipeline(self, project, report, topic):

        try:

            print(f"[AUTO] Starting topic pipeline → Topic ID: {topic.id} | {topic.title}")

            # ---------------------------------------
            # 1️⃣ Generate analysis plan
            # ---------------------------------------
            plan_obj = self.generate_topic_analysis_plan(project, report, topic)

            plan_obj.is_approved = True
            topic.is_approved = True

            topic.save()
            plan_obj.save()

            print(f"[AUTO] Analysis plan generated → Topic {topic.id}")

            # ---------------------------------------
            # 2️⃣ Generate topic content
            # ---------------------------------------
            content_obj = self.content_agent.get_topic_content(topic)

            content_obj = self.generate_topic_content(
                project,
                report,
                topic,
                content_obj,
            )

            print(f"[AUTO] Topic content generated → Topic {topic.id}")

            content_json = content_obj.content_json
            sections = content_json.get("sections", [])

            # ---------------------------------------
            # 3️⃣ Compute SQL / Visual placeholders concurrently
            # ---------------------------------------

            tasks = []

            with ThreadPoolExecutor(max_workers=6) as executor:

                for s_index, section in enumerate(sections):

                    blocks = section.get("content_blocks", [])

                    for b_index, block in enumerate(blocks):

                        if block.get("type") == "sql_placeholder":

                            print(
                                f"[AUTO] SQL placeholder detected → Topic {topic.id} | Section {s_index} Block {b_index}"
                            )

                            tasks.append(
                                executor.submit(
                                    self.compute_sql_block,
                                    project,
                                    report,
                                    topic,
                                    content_obj,
                                    s_index,
                                    b_index,
                                )
                            )

                        elif block.get("type") == "visual_placeholder":

                            print(
                                f"[AUTO] Visual placeholder detected → Topic {topic.id} | Section {s_index} Block {b_index}"
                            )

                            tasks.append(
                                executor.submit(
                                    self.compute_visual_block,
                                    project,
                                    report,
                                    topic,
                                    content_obj,
                                    s_index,
                                    b_index,
                                )
                            )

                for task in tasks:
                    try:
                        task.result()
                    except Exception as e:
                        print(f"[AUTO] Placeholder computation failed → Topic {topic.id}: {e}")

            print(f"[AUTO] Topic pipeline completed → Topic {topic.id}")

        except Exception as e:
            print(f"[AUTO] Topic pipeline crashed → Topic {topic.id}: {e}")

            try:

                # 1 Generate analysis plan
                plan_obj = self.generate_topic_analysis_plan(project, report, topic)

                plan_obj.is_approved = True
                topic.is_approved = True

                topic.save()
                plan_obj.save()

                # 2 Generate topic content
                content_obj = self.content_agent.get_topic_content(topic)

                content_obj = self.generate_topic_content(
                    project,
                    report,
                    topic,
                    content_obj,
                )

                content_json = content_obj.content_json

                sections = content_json.get("sections", [])

                for s_index, section in enumerate(sections):

                    blocks = section.get("content_blocks", [])

                    for b_index, block in enumerate(blocks):

                        try:

                            if block.get("type") == "sql_placeholder":

                                self.compute_sql_block(
                                    project,
                                    report,
                                    topic,
                                    content_obj,
                                    s_index,
                                    b_index,
                                )

                            elif block.get("type") == "visual_placeholder":

                                self.compute_visual_block(
                                    project,
                                    report,
                                    topic,
                                    content_obj,
                                    s_index,
                                    b_index,
                                )

                        except Exception:
                            pass

            except Exception:
                pass