from app.services.metadata_generation.schema_context_builder import build_schema_context
from app.services.metadata_generation.metadata_retriever import retrieve_multi_table_metadata

from app.services.topic_gen.visual_gen.visual_agent_service import (
    generate_visual_plan,
    parse_visual_placeholder,
)
from app.services.topic_gen.visual_gen.visual_renderer import render_visual

from app.services.sql_gen.sql_agent import generate_sql_from_visual_plan
from app.services.sql_gen.sql_executor import execute_sql_safely


SUPPORTED_VISUAL_TYPES = {
    "line_chart",
    "bar_chart",
    "pie_chart",
    "table",
    "combo_chart",
}


class VisualAgent:

    def build_schema_context(self, project):
        """Build schema context"""
        return build_schema_context(project)
    
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
        """Remove visual placeholder"""

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
        """Compute visual block"""

        content_json = content_obj.content_json
        sections = content_json.get("sections", [])

        try:
            visual_block = sections[section_index]["content_blocks"][block_index]

            # Initialize retry metadata
            retry_meta = visual_block.setdefault("retry_meta", {
                "attempts": 0,
                "max_attempts": 3
            })

            retry_meta["attempts"] += 1

            print(f"[VISUAL] Attempt {retry_meta['attempts']} / {retry_meta['max_attempts']}")        
        except (IndexError, KeyError, TypeError):
            raise ValueError("Invalid visual placeholder reference.")

        if visual_block.get("type") != "visual_placeholder":
            raise ValueError("Selected block is not a visual placeholder.")

        schema_context = self.build_schema_context(project)

        try:
            parsed = parse_visual_placeholder(visual_block)
            chart_type = parsed["type"].lower()

            if chart_type not in SUPPORTED_VISUAL_TYPES:
                failed_reason = f"[VISUAL] Unsupported chart type detected: {chart_type}"
                print(failed_reason)

                return self._handle_visual_failure(
                    sections=sections,
                    section_index=section_index,
                    block_index=block_index,
                    content_obj=content_obj,
                    content_json=content_json,
                    retry_meta=retry_meta,
                    reason="Unsupported chart type detected",
                    error=e if 'e' in locals() else None,
                )

        except Exception as e:
            failed_reason = f"[VISUAL] Placeholder parsing failed: {e}"
            print(failed_reason)

            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason=" Placeholder parsing failed",
                error=e if 'e' in locals() else None,
            )
        
        metadata_context = self.retrieve_metadata_context(
            project=project,
            visual_placeholder=visual_block,
            topic_title=topic.title,
        )

        existing_visuals = self._collect_existing_visuals(content_json)

        visual_plan = generate_visual_plan(
            project=project,
            visual_placeholder=visual_block,
            topic_plan=topic.analysis_plan.plan_json,
            metadata_context=metadata_context,
            database_schema=schema_context,
            existing_visuals=existing_visuals,
        )

        visual_spec = visual_plan.get("visual_spec", {})
        generated_type = visual_spec.get("type")

        if generated_type and generated_type not in SUPPORTED_VISUAL_TYPES:
            failed_reason = f"[VISUAL] LLM generated unsupported visual type: {generated_type}"
            print(failed_reason)

            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason="LLM generated unsupported visual type",
                error=e if 'e' in locals() else None,
            )

        if visual_plan["status"] != "ok":
            failed_reason = f"[VISUAL] Placeholder parsing failed: status is not ok"
            print(failed_reason)

            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason=failed_reason,
                error=e if 'e' in locals() else None,
            )

        sql_response = generate_sql_from_visual_plan(
            project=project,
            visual_plan=visual_plan,
            metadata_context=metadata_context,
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

            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason='visual execution failed',
                error=e if 'e' in locals() else None,
            )

        # Validate sql result
        if (
            not sql_result
            or sql_result.get("status") != "ok"
            or sql_result.get("row_count", 0) == 0
            or not sql_result.get("result")
        ):
            print("[VISUAL] Empty SQL result → triggering failure handler")

            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason="Empty SQL result",
                error=None,
            )

        visual_output = render_visual(
            visual_spec=visual_plan["visual_spec"],
            sql_result=sql_result["result"],
        )

        visual_block["generated_visual"] = {
            "status": "ok",
            "visual_spec": visual_plan["visual_spec"],
            "sql_query": sql_response["sql"],
            "figure_json": visual_output["figure_json"],
            "row_count": sql_result["row_count"],
        }

        content_obj.content_json = content_json
        content_obj.save()

        return {
            "success": True,
            "placeholder_removed": False
        }
    
    def _collect_existing_visuals(self, content_json: dict) -> list:
        """Collect existing visuals"""

        existing = []

        # Collect already generated visuals
        for section in content_json.get("sections", []):
            for block in section.get("content_blocks", []):
                gen_visual = block.get("generated_visual")
                if gen_visual and gen_visual.get("status") == "ok":
                    existing.append({
                        "visual_spec": gen_visual.get("visual_spec", {}),
                        "sql_query": gen_visual.get("sql_query", ""),
                    })
        return existing

    def retrieve_metadata_context(
        self,
        *,
        project,
        visual_placeholder: dict,
        topic_title: str,
        k: int = 8,
    ):
        """Retrieve metadata context"""

        query = self._build_metadata_query(
            visual_placeholder=visual_placeholder,
            topic_title=topic_title,
        )

        return retrieve_multi_table_metadata(
            project=project,
            primary_query=query,
            secondary_queries=[
                "visual generation joins relationship-aware dimensions measures time-series categories",
                "chart SQL grouping dimensions analytical capabilities table relationships",
            ],
            per_query_k=k,
            max_docs=max(k * 3, 20),
        )
    

    def _build_metadata_query(self, visual_placeholder: dict, topic_title: str):
        """Build metadata query"""

        try:
            parsed = parse_visual_placeholder(visual_placeholder)
            visual_type = parsed["type"]
            visual_purpose = parsed["purpose"]
        except Exception:
            visual_type = ""
            visual_purpose = ""

        return f"""
        {topic_title}
        {visual_type}
        {visual_purpose}
        dataset columns
        """
    
    def _handle_visual_failure(
        self,
        *,
        sections,
        section_index,
        block_index,
        content_obj,
        content_json,
        retry_meta,
        reason=None,
        visual_plan=None,
        attempted_sql=None,
        error=None,
    ):
        """Handle visual failure"""

        retry_meta.setdefault("errors", [])
        if error:
            retry_meta["errors"].append(str(error))

        if retry_meta["attempts"] >= retry_meta["max_attempts"]:

            print("[VISUAL] Max retries reached → removing placeholder")

            self._remove_visual_placeholder(
                sections,
                section_index,
                block_index,
                reason=reason or "max_retries_exceeded",
                visual_plan=visual_plan,
                attempted_sql=attempted_sql,
                error=error,
            )

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": True
            }

        else:

            print("[VISUAL] Retry scheduled → keeping placeholder")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": False
            }
