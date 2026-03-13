from pathlib import Path
from django.conf import settings

from app.services.visual_agent import generate_visual_plan
from app.services.sql_agent import generate_sql_from_visual_plan
from app.services.sql_executor import execute_sql_safely
from app.services.visual_renderer import render_visual

from app.models import SelectedTable
from app.services.column_introspector import get_table_columns
from app.services.visual_agent import parse_visual_placeholder

SUPPORTED_VISUAL_TYPES = {
    "line_chart",
    "bar_chart",
    "pie_chart",
    "table",
    "combo_chart",
}


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
    
    # -----------------------------------------
    # REMOVE PLACEHOLDER SAFELY
    # -----------------------------------------
    def _remove_visual_placeholder(
        self,
        sections,
        section_index,
        block_index,
        *,
        reason=None,
        visual_plan=None,
        attempted_sql=None,
        error=None,
    ):

        try:
            block = sections[section_index]["content_blocks"][block_index]

            removed_block = {
                "type": "removed_placeholder",
                "placeholder_type": "visual",
                "reason": reason,
                "original_placeholder": block.get("content"),
                "attempted_computation": {
                    "visual_plan": visual_plan,
                    "sql": attempted_sql,
                },
                "error": str(error) if error else None,
            }

            sections[section_index]["content_blocks"][block_index] = removed_block

        except Exception:
            pass


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

        # -----------------------------------------
        # VALIDATE CHART TYPE
        # -----------------------------------------

        try:
            parsed = parse_visual_placeholder(visual_block)
            chart_type = parsed["type"].lower()

            if chart_type not in SUPPORTED_VISUAL_TYPES:

                print(f"[VISUAL] Unsupported chart type detected: {chart_type}")

                self._remove_visual_placeholder(
                    sections,
                    section_index,
                    block_index,
                    reason=f"unsupported_chart_type: {chart_type}",
                )

                content_obj.content_json = content_json
                content_obj.save()

                return {
                    "success": False,
                    "placeholder_removed": True
                }

        except Exception as e:

            print(f"[VISUAL] Placeholder parsing failed: {e}")

            self._remove_visual_placeholder(
                sections,
                section_index,
                block_index,
                reason="invalid_visual_placeholder",
                error=e,
            )

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }

        visual_plan = generate_visual_plan(
            visual_placeholder=visual_block,
            topic_plan=topic.analysis_plan.plan_json,
            metadata_context=content_json.get("metadata_context"),
            database_schema=schema_context,
        )

        visual_spec = visual_plan.get("visual_spec", {})
        generated_type = visual_spec.get("type")

        if generated_type and generated_type not in SUPPORTED_VISUAL_TYPES:

            print(f"[VISUAL] LLM generated unsupported visual type: {generated_type}")

            self._remove_visual_placeholder(
                sections,
                section_index,
                block_index,
                reason=f"llm_generated_invalid_visual: {generated_type}",
                visual_plan=visual_plan,
            )

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }

        if visual_plan["status"] != "ok":
            self._remove_visual_placeholder(sections, section_index, block_index)
            content_obj.content_json = content_json
            content_obj.save()
            return {
                "success": False,
                "placeholder_removed": True
            }

        sql_response = generate_sql_from_visual_plan(
            visual_plan=visual_plan,
            metadata_context=content_json.get("metadata_context"),
            database_schema=schema_context,
        )
        try:

            sql_result = execute_sql_safely(
                sql_response["sql"],
                project_id=project.id,
                expected_result_type="table",
            )

        except Exception as e:

            print("visual execution failed:", e)

            self._remove_visual_placeholder(sections, section_index, block_index, reason="visual execution failed")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }

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

        return {
            "success": True,
            "placeholder_removed": False
        }