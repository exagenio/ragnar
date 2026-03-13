from app.services.sql_agent import generate_sql_from_placeholder
from app.services.sql_executor import execute_sql_safely
from app.services.sql_result_interpreter import interpret_sql_result
from app.models import SelectedTable
from app.services.column_introspector import get_table_columns


class SQLAgent:

    # -----------------------------------------
    # BUILD DATABASE SCHEMA CONTEXT
    # -----------------------------------------
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


    # -----------------------------------------
    # REMOVE PLACEHOLDER SAFELY
    # -----------------------------------------
    def _remove_sql_placeholder(
        self,
        sections,
        section_index,
        block_index,
        *,
        reason=None,
        attempted_sql=None,
        error=None,
    ):

        try:
            block = sections[section_index]["content_blocks"][block_index]

            removed_block = {
                "type": "removed_placeholder",
                "placeholder_type": "sql",
                "reason": reason,
                "original_placeholder": block.get("content"),
                "attempted_computation": {
                    "sql": attempted_sql,
                },
                "error": str(error) if error else None,
            }

            sections[section_index]["content_blocks"][block_index] = removed_block

        except Exception:
            pass


    # -----------------------------------------
    # COMPUTE SQL BLOCK
    # -----------------------------------------
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

        # -----------------------------------------
        # GENERATE SQL FROM PLACEHOLDER
        # -----------------------------------------
        try:

            generated_sql = generate_sql_from_placeholder(
                sql_placeholder=sql_block,
                metadata_context=content_json.get("metadata_context"),
                database_schema=schema_context,
            )

        except Exception as e:

            print("SQL generation failed:", e)

            self._remove_sql_placeholder(sections, section_index, block_index,reason="sql_generation_failed")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }


        # -----------------------------------------
        # SQL AGENT MAY RETURN "not_possible"
        # -----------------------------------------
        if generated_sql.get("status") != "ok":

            print("SQL generation not possible:", generated_sql)

            self._remove_sql_placeholder(sections, section_index, block_index,reason="SQL generation not possible")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }


        # -----------------------------------------
        # EXECUTE SQL
        # -----------------------------------------
        try:

            result = execute_sql_safely(
                generated_sql["sql"],
                project_id=project.id,
                expected_result_type=generated_sql.get("result_type", "scalar"),
            )

        except Exception as e:

            print("SQL execution failed:", e)

            self._remove_sql_placeholder(sections, section_index, block_index, reason="SQL execution failed")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }


        blocks = sections[section_index]["content_blocks"]

        # -----------------------------------------
        # ENSURE PREVIOUS BLOCK EXISTS
        # -----------------------------------------
        if (
            block_index == 0
            or blocks[block_index - 1]["type"]
            not in ["paragraph", "bullet_list"]
        ):

            print("SQL placeholder has no preceding paragraph. Removing.")

            self._remove_sql_placeholder(sections, section_index, block_index,reason="SQL placeholder has no preceding paragraph. Removing.")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }


        previous_block = blocks[block_index - 1]

        # -----------------------------------------
        # INTERPRET SQL RESULT INTO TEXT
        # -----------------------------------------
        try:

            interpreted_text = interpret_sql_result(
                draft_content=previous_block["content"],
                computed_result=result,
            )

            previous_block["content"] = interpreted_text

        except Exception as e:

            print("SQL interpretation failed:", e)

            self._remove_sql_placeholder(sections, section_index, block_index, reason="SQL interpretation failed")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }


        # -----------------------------------------
        # STORE RESULT
        # -----------------------------------------
        sql_block["generated_result"] = {
            "status": "ok",
            "value": result["result"],
            "row_count": result.get("row_count"),
        }

        sql_block["computed"] = True

        content_obj.content_json = content_json
        content_obj.save()

        return {
            "success": False,
            "placeholder_removed": True
        }