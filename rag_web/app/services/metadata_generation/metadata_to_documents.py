import json
from collections import defaultdict
from langchain_core.documents import Document


def metadata_to_documents(metadata_obj):
    """Convert metadata to documents."""

    if metadata_obj.object_type == "enum":
        return enum_metadata_to_documents(metadata_obj)
    return table_metadata_to_documents(metadata_obj)


def table_metadata_to_documents(metadata_obj):
    """Convert table metadata to documents."""

    docs = []
    data = metadata_obj.approved_metadata or {}

    project_id = metadata_obj.project.id
    table = metadata_obj.object_name

    docs.append(
        Document(
            page_content=(
                f"Table {table}. {data.get('table_description', '')} "
                "Use this metadata for topic, section, and subsection queries about this table, "
                "its business entity, measures, dimensions, statuses, timestamps, and joins."
            ),
            metadata={
                "project_id": project_id,
                "table_name": table,
                "type": "table_description",
            },
        )
    )

    for relationship in data.get("table_relationships", []):
        docs.append(
            Document(
                page_content=(
                    f"Relationship for table {table} with {relationship.get('related_table')}: "
                    f"{relationship.get('description', '')} "
                    f"Relationship type: {relationship.get('relationship_type')}."
                ),
                metadata={
                    "project_id": project_id,
                    "table_name": table,
                    "type": "table_relationship",
                    "related_table": relationship.get("related_table"),
                    "relationship_type": relationship.get("relationship_type"),
                    "direction": relationship.get("direction"),
                    "through_table": relationship.get("through_table"),
                },
            )
        )

    for col, col_data in data.get("columns", {}).items():
        if isinstance(col_data, str):
            description = col_data
            semantic_role = "unknown"
            entity_type = None
            dtype = None
            enum_name = None
            accepted_values = []
        else:
            description = col_data.get("description", "")
            semantic_role = col_data.get("semantic_role", "unknown")
            entity_type = col_data.get("entity_type")
            dtype = col_data.get("data_type") or col_data.get("type")
            enum_name = col_data.get("enum_name")
            accepted_values = col_data.get("accepted_values", [])

        docs.append(
            Document(
                page_content=(
                    f"Column {table}.{col}. {description} "
                    f"Data type: {dtype or 'unknown'}. "
                    f"Semantic role: {semantic_role}. "
                    f"Entity type: {entity_type or 'unknown'}. "
                    f"Enum name: {enum_name or 'not_enum'}. "
                    f"Accepted values: {', '.join(str(value) for value in accepted_values) if accepted_values else 'not provided'}."
                ),
                metadata={
                    "project_id": project_id,
                    "table_name": table,
                    "type": "column",
                    "column": col,
                    "semantic_role": semantic_role,
                    "entity_type": entity_type,
                    "data_type": dtype,
                    "enum_name": enum_name,
                },
            )
        )

        for relationship in col_data.get("relationships", []) if isinstance(col_data, dict) else []:
            docs.append(
                Document(
                    page_content=(
                        f"Column relationship for {table}.{col} to "
                        f"{relationship.get('related_table')}.{relationship.get('related_column')}: "
                        f"{relationship.get('description', '')}"
                    ),
                    metadata={
                        "project_id": project_id,
                        "table_name": table,
                        "type": "column_relationship",
                        "column": col,
                        "related_table": relationship.get("related_table"),
                        "related_column": relationship.get("related_column"),
                        "relationship_type": relationship.get("relationship_type"),
                    },
                )
            )

    semantic_roles = defaultdict(list)
    entity_types = set()
    join_paths = []

    for col_name, col_data in data.get("columns", {}).items():
        if isinstance(col_data, str):
            role = "unknown"
            entity_type = None
            normalized_col = {
                "column": col_name,
                "description": col_data,
                "semantic_role": role,
            }
        else:
            role = col_data.get("semantic_role", "unknown")
            entity_type = col_data.get("entity_type")
            normalized_col = {
                "column": col_name,
                **col_data,
            }

        semantic_roles[role].append(normalized_col)

        if entity_type:
            entity_types.add(entity_type)

        if isinstance(col_data, dict):
            for relationship in col_data.get("relationships", []):
                join_paths.append(
                    {
                        "column": col_name,
                        "related_table": relationship.get("related_table"),
                        "related_column": relationship.get("related_column"),
                        "relationship_type": relationship.get("relationship_type"),
                    }
                )

    docs.append(
        Document(
            page_content=json.dumps(
                {
                    "time_columns": [c for c in semantic_roles.get("time", [])],
                    "measure_columns": [c for c in semantic_roles.get("measure", [])],
                    "entity_types": list(entity_types),
                    "join_paths": join_paths,
                    "table_relationships": data.get("table_relationships", []),
                }
            ),
            metadata={
                "project_id": project_id,
                "table_name": table,
                "type": "analytical_capability",
            },
        )
    )

    for note in data.get("confidence_notes", []):
        docs.append(
            Document(
                page_content=f"Table {table} confidence note: {note}",
                metadata={
                    "project_id": project_id,
                    "table_name": table,
                    "type": "confidence_note",
                },
            )
        )

    return docs


def enum_metadata_to_documents(metadata_obj):
    """Convert enum metadata to documents."""

    docs = []
    data = metadata_obj.approved_metadata or {}
    project_id = metadata_obj.project.id
    enum_name = metadata_obj.object_name
    enum_values = data.get("enum_values", [])
    usage_contexts = data.get("usage_contexts", [])
    ordered_values = [item.get("value") for item in enum_values if item.get("value") is not None]
    usage_summary = "; ".join(
        f"{usage.get('table_name')}.{usage.get('column_name')}"
        for usage in usage_contexts
        if usage.get("table_name") and usage.get("column_name")
    )

    docs.append(
        Document(
            page_content=(
                f"Enum {enum_name}. {data.get('enum_description', '')} "
                f"Full ordered enum values: {', '.join(str(value) for value in ordered_values) if ordered_values else 'not provided'}. "
                f"Used by: {usage_summary or 'no usage context provided'}. "
                "This enum represents a controlled categorical domain that can be referenced "
                "from topic, section, and subsection queries. "
                "Use the complete enum value set when building logic, filters, statuses, transitions, and relationships."
            ),
            metadata={
                "project_id": project_id,
                "enum_name": enum_name,
                "type": "enum_description",
                "table_name": metadata_obj.source_table or "",
                "column": metadata_obj.source_column or "",
            },
        )
    )

    docs.append(
        Document(
            page_content=json.dumps(
                {
                    "enum_name": enum_name,
                    "all_values": ordered_values,
                    "usage_contexts": usage_contexts,
                    "enum_description": data.get("enum_description", ""),
                }
            ),
            metadata={
                "project_id": project_id,
                "enum_name": enum_name,
                "type": "enum_usage",
                "table_name": metadata_obj.source_table or "",
                "column": metadata_obj.source_column or "",
            },
        )
    )

    for enum_value in enum_values:
        docs.append(
            Document(
                page_content=(
                    f"Enum {enum_name} value {enum_value.get('value')}. "
                    f"{enum_value.get('description', '')} "
                    f"Usage hint: {enum_value.get('usage_hint', '')}"
                ),
                metadata={
                    "project_id": project_id,
                    "enum_name": enum_name,
                    "type": "enum_value",
                    "table_name": metadata_obj.source_table or "",
                    "column": metadata_obj.source_column or "",
                    "enum_value": enum_value.get("value"),
                },
            )
        )

    for usage in usage_contexts:
        docs.append(
            Document(
                page_content=(
                    f"Enum {enum_name} is used by {usage.get('table_name')}.{usage.get('column_name')}. "
                    f"{usage.get('description', '')} "
                    f"Column data type: {usage.get('column_type', 'unknown')}."
                ),
                metadata={
                    "project_id": project_id,
                    "enum_name": enum_name,
                    "type": "enum_usage",
                    "table_name": usage.get("table_name"),
                    "column": usage.get("column_name"),
                },
            )
        )

    for note in data.get("confidence_notes", []):
        docs.append(
            Document(
                page_content=f"Enum {enum_name} confidence note: {note}",
                metadata={
                    "project_id": project_id,
                    "enum_name": enum_name,
                    "type": "confidence_note",
                    "table_name": metadata_obj.source_table or "",
                    "column": metadata_obj.source_column or "",
                },
            )
        )

    return docs
