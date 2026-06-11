import json
from decimal import Decimal
from datetime import date, datetime

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from langchain_core.documents import Document


DEFAULT_CHUNK_SIZE = 10
DEFAULT_DOCUMENT_BATCH_SIZE = 100
MAX_CHUNK_CHARS = 12000


def _chunk_rows(rows, max_rows, max_chars):
    """Yield row groups split by maximum row count and character length."""

    current_rows = []
    current_chars = 0

    for row in rows:
        row_text = json.dumps(row, ensure_ascii=False)
        if current_rows and (
            len(current_rows) >= max_rows
            or current_chars + len(row_text) > max_chars
        ):
            yield current_rows
            current_rows = []
            current_chars = 0

        current_rows.append(row)
        current_chars += len(row_text)

    if current_rows:
        yield current_rows


def table_data_to_documents(project, table_name, chunk_size=DEFAULT_CHUNK_SIZE):
    """Return all row-group documents for vector retrieval."""

    docs = []
    for batch, _, _, _ in iter_table_data_document_batches(
        project,
        table_name,
        chunk_size=chunk_size,
    ):
        docs.extend(batch)

    return docs


def iter_table_data_document_batches(
    project,
    table_name,
    *,
    chunk_size=DEFAULT_CHUNK_SIZE,
    document_batch_size=DEFAULT_DOCUMENT_BATCH_SIZE,
):
    """Stream a full table as provider-safe batches of row-group documents."""

    project_id = project.id
    db_connection = project.db_connection

    conn = psycopg2.connect(
        host=db_connection.host,
        port=db_connection.port,
        dbname=db_connection.database_name,
        user=db_connection.username,
        password=db_connection.password,
    )

    cursor = None
    try:
        cursor = conn.cursor(
            name=f"table_data_{project_id}",
            cursor_factory=RealDictCursor,
        )
        cursor.itersize = chunk_size
        cursor.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name)))

        chunk_index = 0
        batch_docs = []
        batch_ids = []
        batch_start_index = 0

        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break

            normalized_rows = [_normalize_row(row) for row in rows]

            for row_group in _chunk_rows(
                normalized_rows,
                max_rows=chunk_size,
                max_chars=MAX_CHUNK_CHARS,
            ):
                columns = list(row_group[0].keys()) if row_group else []
                content = {
                    "table_name": table_name,
                    "chunk_index": chunk_index,
                    "columns": columns,
                    "rows": row_group,
                }

                batch_docs.append(
                    Document(
                        page_content=json.dumps(content, ensure_ascii=False),
                        metadata={
                            "project_id": project_id,
                            "table_name": table_name,
                            "type": "table_data_chunk",
                            "chunk_index": chunk_index,
                            "row_count": len(row_group),
                        },
                    )
                )
                batch_ids.append(table_data_document_id(project_id, table_name, chunk_index))
                chunk_index += 1

            if len(batch_docs) >= document_batch_size:
                yield batch_docs, batch_ids, batch_start_index, chunk_index
                batch_docs = []
                batch_ids = []
                batch_start_index = chunk_index

        if batch_docs:
            yield batch_docs, batch_ids, batch_start_index, chunk_index
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        conn.close()


def table_data_document_ids(project_id, table_name, count):
    """Return deterministic ids so repeated metadata generation updates chunks."""

    return [
        table_data_document_id(project_id, table_name, index)
        for index in range(count)
    ]


def table_data_document_id(project_id, table_name, index):
    """Return a deterministic id for one table data chunk."""

    safe_table = str(table_name).replace(" ", "_")
    return f"project:{project_id}:table:{safe_table}:data_chunk:{index}"


def _normalize_row(row):
    return {key: _json_safe(value) for key, value in dict(row).items()}


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
