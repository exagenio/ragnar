import json

from app.models import SelectedTable
from app.services.llm_config.llm_provider import LLMBackend
from app.services.vector_db_config.vector_store import get_vector_store


DEFAULT_METADATA_TYPES = [
    "table_description",
    "table_relationship",
    "column",
    "column_relationship",
    "analytical_capability",
    "confidence_note",
]

TYPE_PRIORITY = {
    "table_relationship": 0,
    "column_relationship": 1,
    "analytical_capability": 2,
    "table_description": 3,
    "column": 4,
    "confidence_note": 5,
}


def get_selected_table_names(project):
    """Return selected table names for the project."""

    return list(
        SelectedTable.objects.filter(project=project)
        .order_by("created_at", "table_name")
        .values_list("table_name", flat=True)
    )


def get_dataset_mode(project):
    """Return whether the project uses a single-table or multi-table dataset."""

    table_count = SelectedTable.objects.filter(project=project).count()
    if table_count <= 1:
        return "single_table"
    return "multi_table"


def retrieve_multi_table_metadata(
    *,
    project,
    primary_query: str,
    secondary_queries=None,
    metadata_types=None,
    per_query_k: int = 8,
    max_docs: int = 24,
    backend: LLMBackend | None = None,
):
    """Retrieve metadata context that adapts to single-table and multi-table datasets."""

    metadata_types = metadata_types or DEFAULT_METADATA_TYPES
    secondary_queries = secondary_queries or []

    vector_store = get_vector_store(backend=backend)
    selected_tables = get_selected_table_names(project)
    dataset_mode = get_dataset_mode(project)
    selected_tables_text = " ".join(selected_tables)

    if dataset_mode == "multi_table":
        mode_specific_query = (
            f"{primary_query}\n"
            f"Selected tables: {selected_tables_text}\n"
            "Focus on joins, foreign keys, relationship types, entity links, "
            "time dimensions, measures, and cross-table analytical paths."
        ).strip()
        default_supporting_query = (
            f"{selected_tables_text}\n"
            "database schema relationships joins foreign keys one-to-many "
            "many-to-many one-to-one analytical capabilities"
        ).strip()
    else:
        mode_specific_query = (
            f"{primary_query}\n"
            f"Selected table: {selected_tables_text}\n"
            "Focus on the business meaning of this table, its measures, "
            "dimensions, time fields, identifiers, and analytical capabilities. "
            "Do not force join logic when no related tables are selected."
        ).strip()
        default_supporting_query = (
            f"{selected_tables_text}\n"
            "single table dataset business entities measures dimensions "
            "time columns identifiers analytical capabilities"
        ).strip()

    query_bundle = [
        primary_query.strip(),
        mode_specific_query,
        default_supporting_query,
        *[query.strip() for query in secondary_queries if query and query.strip()],
    ]

    docs = []
    for query in query_bundle:
        docs.extend(
            vector_store.similarity_search(
                query,
                k=per_query_k,
                filter={
                    "project_id": project.id,
                    "type": metadata_types,
                },
            )
        )

    unique_docs = []
    seen = set()
    for doc in docs:
        metadata = dict(doc.metadata or {})
        key = (
            metadata.get("type"),
            metadata.get("table_name"),
            metadata.get("column"),
            metadata.get("related_table"),
            metadata.get("related_column"),
            doc.page_content,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_docs.append(doc)

    unique_docs.sort(
        key=lambda doc: (
            TYPE_PRIORITY.get(doc.metadata.get("type"), 99),
            doc.metadata.get("table_name", ""),
            doc.metadata.get("column", ""),
        )
    )

    return [
        {
            "content": doc.page_content,
            "metadata": dict(doc.metadata or {}),
        }
        for doc in unique_docs[:max_docs]
    ]


def build_retrieved_context(metadata_context) -> str:
    """Render metadata context as grouped text for prompts."""

    grouped = {}

    for item in metadata_context:
        metadata = item.get("metadata", {})
        table = metadata.get("table_name") or metadata.get("related_table") or "schema"
        grouped.setdefault(table, []).append(item)

    output = []
    for table, items in grouped.items():
        output.append(f"### Table: {table}")
        for item in items:
            metadata = item.get("metadata", {})
            output.append(f"- Type: {metadata.get('type')}")
            if metadata.get("column"):
                output.append(f"  Column: {metadata['column']}")
            if metadata.get("related_table"):
                relation_line = f"  Related table: {metadata['related_table']}"
                if metadata.get("related_column"):
                    relation_line += f".{metadata['related_column']}"
                output.append(relation_line)
            output.append(f"  {item.get('content', '')}")

    return "\n".join(output)


def format_metadata_context_json(metadata_context) -> str:
    """Format metadata context for prompt injection."""

    return json.dumps(metadata_context, indent=2)
