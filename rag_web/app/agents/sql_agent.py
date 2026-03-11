from app.services.sql_agent import generate_sql_from_placeholder
from app.services.sql_agent import generate_sql_from_visual_plan
from app.services.sql_executor import execute_sql_safely
from app.services.sql_result_interpreter import interpret_sql_result
from app.models import SelectedTable
from app.services.column_introspector import get_table_columns


class SQLAgent:

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


    def compute_sql_block(
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
            sql_block = sections[section_index]["content_blocks"][block_index]
        except (IndexError, KeyError, TypeError):
            raise ValueError("Invalid SQL placeholder reference.")

        if sql_block.get("type") != "sql_placeholder":
            raise ValueError("Selected block is not a SQL placeholder.")

        schema_context = self.build_schema_context(project)

        generated_sql = generate_sql_from_placeholder(
            sql_placeholder=sql_block,
            metadata_context=content_json.get("metadata_context"),
            database_schema=schema_context,
        )

        result = execute_sql_safely(
            generated_sql["sql"],
            project_id=project.id,
            expected_result_type=generated_sql["result_type"],
        )

        blocks = sections[section_index]["content_blocks"]

        if block_index == 0 or blocks[block_index - 1]["type"] not in ["paragraph", "bullet_list"]:
            raise ValueError("No paragraph or bullet list found to attach SQL result.")

        previous_block = blocks[block_index - 1]

        interpreted_text = interpret_sql_result(
            draft_content=previous_block["content"],
            computed_result=result,
        )

        previous_block["content"] = interpreted_text

        sql_block["generated_result"] = {
            "status": "ok",
            "value": result["result"],
            "row_count": result.get("row_count"),
        }

        sql_block["computed"] = True

        content_obj.content_json = content_json
        content_obj.save()

        return True