from app.services.project_service import ProjectService
from app.agents.metadata_agent import MetadataAgent
from app.agents.content_agent import ContentAgent
from app.agents.sql_agent import SQLAgent
from app.agents.visual_Agent import VisualAgent

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
    
    def compute_sql_block(self, project, topic, content_obj, section_index, block_index):
        return self.sql_agent.compute_sql_block(
            project,
            topic,
            content_obj,
            section_index,
            block_index,
        )

    def compute_visual_block(self, project, topic, content_obj, section_index, block_index):
        return self.visual_agent.compute_visual_block(
            project,
            topic,
            content_obj,
            section_index,
            block_index,
        )
    
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