from pathlib import Path
from django.conf import settings

from app.services.visual_agent import generate_visual_plan
from app.services.sql_agent import generate_sql_from_visual_plan
from app.services.sql_executor import execute_sql_safely
from app.services.visual_renderer import render_visual

from app.models import SelectedTable
from app.services.column_introspector import get_table_columns


class VisualAgent:

    def build_schema_context(self, project):

        tables = SelectedTable.objects.filter(project=project)

        schema_context = []

        for t in tables:
            columns = get_table_columns(project.db_connection, t.table_name)

            schema_context.append({
                "table": t.table_name,
                "columns": [
                    {"name": col["name"], "type": col["type"]}
                    for col in columns
                ],
            })

        return schema_context


    def compute_visual_block(
        self,
        project,
        topic,
        content_obj,
        section_index,
        block_index,
    ):

        content_json = content_obj.content_json
        sections = content_json.get("sections", [])

        try:
            visual_block = sections[section_index]["content_blocks"][block_index]
        except (IndexError, KeyError, TypeError):
            raise ValueError("Invalid visual placeholder reference.")

        if visual_block.get("type") != "visual_placeholder":
            raise ValueError("Selected block is not a visual placeholder.")

        schema_context = self.build_schema_context(project)

        visual_plan = generate_visual_plan(
            visual_placeholder=visual_block,
            topic_plan=topic.analysis_plan.plan_json,
            metadata_context=content_json.get("metadata_context"),
            database_schema=schema_context,
        )

        if visual_plan["status"] != "ok":
            visual_block["generated_visual"] = visual_plan
            content_obj.save()
            return False

        sql_response = generate_sql_from_visual_plan(
            visual_plan=visual_plan,
            metadata_context=content_json.get("metadata_context"),
            database_schema=schema_context,
        )

        sql_result = execute_sql_safely(
            sql_response["sql"],
            project_id=project.id,
            expected_result_type="table",
        )

        relative_path = (
            Path("generated_visuals")
            / f"project_{project.id}"
            / f"topic_{topic.id}"
            / f"section_{section_index}_block_{block_index}.png"
        )

        output_path = Path(settings.MEDIA_ROOT) / relative_path

        render_visual(
            visual_spec=visual_plan["visual_spec"],
            sql_result=sql_result["result"],
            output_path=output_path,
        )

        visual_block["generated_visual"] = {
            "status": "ok",
            "visual_spec": visual_plan["visual_spec"],
            "image_path": f"{settings.MEDIA_URL}{relative_path.as_posix()}",
            "row_count": sql_result["row_count"],
        }

        content_obj.content_json = content_json
        content_obj.save()

        return True