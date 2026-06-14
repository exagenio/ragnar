from concurrent.futures import ThreadPoolExecutor

from app.services.metadata_generation.schema_context_builder import build_schema_context
from app.services.metadata_generation.metadata_retriever import retrieve_multi_table_metadata

from app.services.sql_gen.sql_agent import (
    generate_sql_for_precomputed_placeholder,
    parse_sql_placeholder,
    generate_sql_placeholders_from_plan,
)
from app.services.sql_gen.sql_executor import execute_sql_safely
from app.services.sql_gen.sql_result_interpreter import interpret_sql_result


class SQLAgent:

    def build_schema_context(self, project):
        """Build schema context"""
        return build_schema_context(project)


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
        """Remove sql placeholder"""

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


    def generate_sql_placeholders_from_plan(
        self,
        *,
        topic_plan: dict,
        project,
        metadata_context: list,
    ):
        """Generate sql placeholders"""

        # Build schema and call service
        schema_context = self.build_schema_context(project)

        result = generate_sql_placeholders_from_plan(
            topic_plan=topic_plan,
            project=project,
            metadata_context=metadata_context,
            schema_context=schema_context,
        )

        return result
    

    def compute_precomputed_sql_placeholders(
        self,
        *,
        project,
        topic_content_obj,
        topic,
    ):
        """Compute precomputed sql placeholders"""

        content_json = topic_content_obj.content_json or {}

        placeholders = content_json.get("precomputed_sql_placeholders", [])
        if not placeholders:
            return topic_content_obj

        schema_context = self.build_schema_context(project)

        results = []

        max_workers = 2  

        with ThreadPoolExecutor(max_workers=max_workers) as executor:

            futures = [
                executor.submit(
                    self._process_single_placeholder,
                    project=project,
                    topic=topic,
                    schema_context=schema_context,
                    placeholder=p,
                )
                for p in placeholders
            ]

        results = [future.result() for future in futures]


        # LLM insight generation for batched results
        batch_size = 2
        final_results = []

        for i in range(0, len(results), batch_size):

            batch = results[i:i+batch_size]

            try:
                interpreted = interpret_sql_result(
                    project=project,
                    placeholders=batch,
                )

                mapping = {
                    str(r["id"]).strip(): r["insights"]
                    for r in interpreted.get("results", [])
                }

                for p in batch:
                    pid = str(p.get("content", {}).get("id")).strip()

                    if pid in mapping:
                        p["content"]["query"]["insights"] = mapping[pid]
                        p["content"]["query"].pop("result", None)

            except Exception as e:
                print(f"[INSIGHT ERROR] {str(e)}")

            final_results.extend(batch)


        # Save computed results back
        content_json["precomputed_sql_placeholders"] = final_results

        topic_content_obj.content_json = content_json
        topic_content_obj.save()
        print("[SQL Calculation ] generateda and computed all the numerical values for the content")
        return topic_content_obj

    def _process_single_placeholder(
        self,
        *,
        project,
        topic,
        schema_context,
        placeholder,
    ):
        """Process single placeholder"""

        try:
            # Retrieve metadata context
            metadata_context = self.retrieve_metadata_context(
                project=project,
                sql_placeholder=placeholder,
                topic_title=topic.title,
            )

            # Generate sql
            generated_sql = generate_sql_for_precomputed_placeholder(
                project=project,
                sql_placeholder=placeholder,
                metadata_context=metadata_context,
                database_schema=schema_context,
            )

            if generated_sql.get("status") != "ok":
                placeholder.setdefault("content", {})["query"] = {
                    "status": "failed",
                    "reason": generated_sql.get("reason", "sql_not_possible"),
                }
                return placeholder

            # Execute sql
            execution = execute_sql_safely(
                generated_sql["sql"],
                project_id=project.id,
                expected_result_type=generated_sql.get("result_type", "scalar"),
            )

            # Attach result
            placeholder.setdefault("content", {})["query"] = {
                "status": "ok",
                "result": execution["result"],
                "row_count": execution.get("row_count"),
                "sql": generated_sql["sql"],
            }

        except Exception as e:
            placeholder.setdefault("content", {})["query"] = {
                "status": "failed",
                "error": str(e),
            }

        return placeholder


    def retrieve_metadata_context(
        self,
        *,
        project,
        sql_placeholder: dict,
        topic_title: str,
        k: int = 8,
    ):
        """Retrieve metadata context"""

        query = self._build_metadata_query(
            sql_placeholder=sql_placeholder,
            topic_title=topic_title,
        )

        return retrieve_multi_table_metadata(
            project=project,
            primary_query=query,
            secondary_queries=[
                "sql query generation joins relationship types business metrics measures dimensions",
                "numerical insight generation analytical capability join paths aggregations",
            ],
            per_query_k=k,
            max_docs=max(k * 3, 20),
        )


    def _build_metadata_query(self, sql_placeholder: dict, topic_title: str):
        """Build metadata query"""

        try:
            parsed = parse_sql_placeholder(sql_placeholder)

            calculation = parsed.get("calculation", "")
            description = parsed.get("description", "")

        except Exception:
            calculation = ""
            description = ""

        return f"""
        {topic_title}
        {calculation}
        {description}
        database columns dataset schema
        """


    def _handle_sql_failure(
        self,
        *,
        sections,
        section_index,
        block_index,
        content_obj,
        content_json,
        retry_meta,
        reason=None,
        attempted_sql=None,
        error=None,
    ):
        """Handle sql failure"""

        if error:
            retry_meta["errors"].append(str(error))

        if retry_meta["attempts"] >= retry_meta["max_attempts"]:

            print("[SQL] Max retries reached → removing placeholder")

            self._remove_sql_placeholder(
                sections,
                section_index,
                block_index,
                reason=reason or "max_retries_exceeded",
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

            print("[SQL] Retry scheduled → keeping placeholder")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": False
            }
