from .table_data_to_documents import iter_table_data_document_batches
from ...models import Project, SelectedTable
from app.services.llm_config.llm_provider import LLMBackend
from app.services.vector_db_config.vector_store import get_vector_store
from app.services.task_tracker import (
    complete_background_task,
    fail_background_task,
    log_background_task,
    start_background_task,
)


def run_metadata_generation(project_id, task_id=None):
    """Run metadata generation"""

    project = Project.objects.get(id=project_id)
    selected_tables = list(SelectedTable.objects.filter(project=project))

    if task_id:
        start_background_task(
            task_id,
            f"Metadata generation started for {len(selected_tables)} selected table(s).",
        )

    try:
        if not selected_tables:
            message = "No selected tables were found for metadata generation."
            if task_id:
                fail_background_task(task_id, message)
            return

        embedding_backend = LLMBackend.LOCAL

        if task_id:
            log_background_task(
                task_id,
                f"Using {embedding_backend.value} embeddings for full dataset vector storage.",
            )

        vector_store = get_vector_store(backend=embedding_backend)

        for table in selected_tables:
            if task_id:
                log_background_task(
                    task_id,
                    f"Chunking and storing full table data for '{table.table_name}' into vector DB.",
                )

            total_chunks = 0
            total_rows = 0

            # Stream table rows and store in batches; this avoids loading sample rows or invoking LLMs
            for docs_batch, doc_ids, start_index, end_index in iter_table_data_document_batches(
                project,
                table.table_name,
            ):
                vector_store.add_documents(
                    docs_batch,
                    ids=doc_ids,
                )

                total_chunks = end_index
                total_rows += sum(doc.metadata.get("row_count", 0) for doc in docs_batch)

                if task_id:
                    log_background_task(
                        task_id,
                        f"Stored table data chunks {start_index + 1}-{end_index} for '{table.table_name}'.",
                    )

            if task_id:
                log_background_task(
                    task_id,
                    f"Stored {total_chunks} table data chunk(s) covering {total_rows} row(s) for '{table.table_name}' in the vector database.",
                    level="success",
                )

        if task_id:
            complete_background_task(task_id, "Metadata generation completed.")
    except Exception as exc:
        if task_id:
            fail_background_task(task_id, f"Metadata generation failed: {exc}")
        raise
