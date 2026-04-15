# sql agent file
from app.services.sql_agent import generate_sql_for_precomputed_placeholder
from app.services.sql_executor import execute_sql_safely
from app.services.sql_result_interpreter import interpret_sql_result
from app.models import SelectedTable
from app.services.column_introspector import get_table_columns
from app.services.vector_store import get_vector_store
from app.services.sql_agent import parse_sql_placeholder
from app.services.sql_agent import generate_sql_placeholders_from_plan
from concurrent.futures import ThreadPoolExecutor, as_completed



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


    def generate_sql_placeholders_from_plan(
        self,
        *,
        topic_plan: dict,
        project,
        metadata_context: list,
    ):
        """
        Wrapper around service-layer placeholder generation.
        """

        # -------------------------
        # Build schema (agent responsibility)
        # -------------------------
        schema_context = self.build_schema_context(project)

        # -------------------------
        # Call service function
        # -------------------------
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
        content_json = topic_content_obj.content_json or {}

        placeholders = content_json.get("precomputed_sql_placeholders", [])
        if not placeholders:
            return topic_content_obj

        schema_context = self.build_schema_context(project)

        results = []

        # max concurrent task at once
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


        # -----------------------------------------
        # STEP: LLM INSIGHT GENERATION
        # -----------------------------------------

        from app.services.sql_result_interpreter import interpret_sql_result

        batch_size = 2
        final_results = []

        for i in range(0, len(results), batch_size):

            batch = results[i:i+batch_size]

            try:
                interpreted = interpret_sql_result(placeholders=batch)

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


        # -------------------------
        # SAVE BACK
        # -------------------------
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
        try:
            # STEP 1: metadata
            metadata_context = self.retrieve_metadata_context(
                project_id=project.id,
                sql_placeholder=placeholder,
                topic_title=topic.title,
            )

            # STEP 2: SQL generation
            generated_sql = generate_sql_for_precomputed_placeholder(
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

            # STEP 3: execute
            execution = execute_sql_safely(
                generated_sql["sql"],
                project_id=project.id,
                expected_result_type=generated_sql.get("result_type", "scalar"),
            )

            # STEP 4: attach
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

    # -----------------------------------------
    # METADATA RETRIEVAL FROM VECTOR DB
    # -----------------------------------------
    def retrieve_metadata_context(
        self,
        *,
        project_id: int,
        sql_placeholder: dict,
        topic_title: str,
        k: int = 8,
    ):
        """
        Retrieve relevant metadata for SQL generation
        using semantic search.
        """

        vector_store = get_vector_store()

        query = self._build_metadata_query(
            sql_placeholder=sql_placeholder,
            topic_title=topic_title,
        )

        docs = vector_store.similarity_search(
            query,
            k=k,
            filter={"project_id": project_id},
        )

        return [
            {
                "content": d.page_content,
                "metadata": d.metadata,
            }
            for d in docs
        ]


    def _build_metadata_query(self, sql_placeholder: dict, topic_title: str):
        """
        Build semantic query to retrieve relevant metadata.
        """

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

        if error:
            retry_meta["errors"].append(str(error))

        # -----------------------------
        # MAX RETRIES → REMOVE
        # -----------------------------
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

        # -----------------------------
        # RETRY LATER
        # -----------------------------
        else:

            print("[SQL] Retry scheduled → keeping placeholder")

            content_obj.content_json = content_json
            content_obj.save()

            return {
                "success": False,
                "placeholder_removed": False
            }