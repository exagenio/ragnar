from app.services.topic_gen.visual_gen.visual_agent_service import (
    generate_visual_plan,
    parse_visual_placeholder,
)
from app.services.topic_gen.visual_gen.visual_renderer import render_visual
from app.services.vector_db_config.vector_store import get_vector_store


SUPPORTED_VISUAL_TYPES = {
    "line_chart",
    "bar_chart",
    "pie_chart",
    "table",
    "combo_chart",
}


class VisualAgent:
    def _remove_visual_placeholder(
        self,
        sections,
        section_index,
        block_index,
        *,
        reason=None,
        visual_plan=None,
        error=None,
    ):
        """Replace a failed visual placeholder with diagnostic information."""

        try:
            block = sections[section_index]["content_blocks"][block_index]
            sections[section_index]["content_blocks"][block_index] = {
                "type": "removed_placeholder",
                "placeholder_type": "visual",
                "reason": reason,
                "original_placeholder": block.get("content"),
                "attempted_computation": {
                    "visual_plan": visual_plan,
                    "calculation_method": "llm_from_vector_retrieval",
                },
                "error": str(error) if error else None,
            }
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
        """Calculate and render a visual from vector-retrieved dataset rows."""

        content_json = content_obj.content_json
        sections = content_json.get("sections", [])

        try:
            visual_block = sections[section_index]["content_blocks"][block_index]
        except (IndexError, KeyError, TypeError) as exc:
            raise ValueError("Invalid visual placeholder reference.") from exc

        if visual_block.get("type") != "visual_placeholder":
            raise ValueError("Selected block is not a visual placeholder.")

        retry_meta = visual_block.setdefault(
            "retry_meta",
            {"attempts": 0, "max_attempts": 3, "errors": []},
        )
        retry_meta["attempts"] += 1

        try:
            parsed = parse_visual_placeholder(visual_block)
            chart_type = parsed["type"].lower()
        except Exception as exc:
            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason="Visual placeholder parsing failed",
                error=exc,
            )

        if chart_type not in SUPPORTED_VISUAL_TYPES:
            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason=f"Unsupported visual type: {chart_type}",
            )

        retrieved_data_context = self.retrieve_metadata_context(
            project_id=project.id,
            visual_placeholder=visual_block,
            topic_title=topic.title,
        )

        if not retrieved_data_context:
            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason="No relevant dataset rows were retrieved",
            )

        visual_plan = None
        try:
            visual_plan = generate_visual_plan(
                project=project,
                visual_placeholder=visual_block,
                topic_plan=topic.analysis_plan.plan_json,
                retrieved_data_context=retrieved_data_context,
                existing_visuals=self._collect_existing_visuals(content_json),
            )

            if visual_plan.get("status") != "ok":
                return self._handle_visual_failure(
                    sections=sections,
                    section_index=section_index,
                    block_index=block_index,
                    content_obj=content_obj,
                    content_json=content_json,
                    retry_meta=retry_meta,
                    reason=visual_plan.get(
                        "reason",
                        "The retrieved rows could not support the visual",
                    ),
                    visual_plan=visual_plan,
                )

            visual_spec = visual_plan["visual_spec"]
            if visual_spec.get("type") not in SUPPORTED_VISUAL_TYPES:
                raise ValueError(
                    f"Unsupported generated visual type: {visual_spec.get('type')}"
                )

            visual_data = visual_plan["visual_data"]
            visual_output = render_visual(
                visual_spec=visual_spec,
                visual_data=visual_data,
            )
        except Exception as exc:
            return self._handle_visual_failure(
                sections=sections,
                section_index=section_index,
                block_index=block_index,
                content_obj=content_obj,
                content_json=content_json,
                retry_meta=retry_meta,
                reason="LLM visual calculation or rendering failed",
                visual_plan=visual_plan,
                error=exc,
            )

        visual_block["generated_visual"] = {
            "status": "ok",
            "visual_spec": visual_spec,
            "visual_data": visual_data,
            "calculation_summary": visual_plan.get("calculation_summary", ""),
            "calculation_method": "llm_from_vector_retrieval",
            "figure_json": visual_output["figure_json"],
            "row_count": len(visual_data["rows"]),
        }

        content_obj.content_json = content_json
        content_obj.save()

        return {
            "success": True,
            "placeholder_removed": False,
        }

    def _collect_existing_visuals(self, content_json):
        existing = []
        for section in content_json.get("sections", []):
            for block in section.get("content_blocks", []):
                generated = block.get("generated_visual")
                if generated and generated.get("status") == "ok":
                    existing.append(
                        {
                            "visual_spec": generated.get("visual_spec", {}),
                            "calculation_summary": generated.get(
                                "calculation_summary",
                                "",
                            ),
                        }
                    )
        return existing

    def retrieve_metadata_context(
        self,
        *,
        project_id,
        visual_placeholder,
        topic_title,
        k=30,
    ):
        """Retrieve full-dataset row chunks for the requested visual."""

        query = self._build_metadata_query(
            visual_placeholder=visual_placeholder,
            topic_title=topic_title,
        )
        docs = get_vector_store().similarity_search(
            f"{query} full dataset rows values calculate visualization",
            k=k,
            filter={
                "project_id": project_id,
                "type": "table_data_chunk",
            },
        )
        return [{"content": doc.page_content} for doc in docs]

    def _build_metadata_query(self, visual_placeholder, topic_title):
        try:
            parsed = parse_visual_placeholder(visual_placeholder)
            visual_type = parsed["type"]
            visual_purpose = parsed["purpose"]
        except Exception:
            visual_type = ""
            visual_purpose = ""

        return f"{topic_title} {visual_type} {visual_purpose}"

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
        error=None,
    ):
        retry_meta.setdefault("errors", [])
        if error:
            retry_meta["errors"].append(str(error))

        if retry_meta["attempts"] >= retry_meta["max_attempts"]:
            self._remove_visual_placeholder(
                sections,
                section_index,
                block_index,
                reason=reason or "max_retries_exceeded",
                visual_plan=visual_plan,
                error=error,
            )
            placeholder_removed = True
        else:
            placeholder_removed = False

        content_obj.content_json = content_json
        content_obj.save()

        return {
            "success": False,
            "placeholder_removed": placeholder_removed,
        }
