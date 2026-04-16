import json
from collections import defaultdict
from langchain_core.documents import Document


def metadata_to_documents(metadata_obj):
    """Convert metadata to documents"""

    docs = []
    data = metadata_obj.approved_metadata

    project_id = metadata_obj.project.id
    table = metadata_obj.table_name

    # Add table description document
    docs.append(
        Document(
            page_content=data["table_description"],
            metadata={
                "project_id": project_id,
                "table_name": table,
                "type": "table_description",
            },
        )
    )

    # Process column descriptions and metadata
    for col, col_data in data["columns"].items():

        # Handle backward compatibility for column structure
        if isinstance(col_data, str):
            description = col_data
            semantic_role = "unknown"
            entity_type = None
        else:
            description = col_data.get("description", "")
            semantic_role = col_data.get("semantic_role", "unknown")
            entity_type = col_data.get("entity_type")

        docs.append(
            Document(
                page_content=description,
                metadata={
                    "project_id": project_id,
                    "table_name": table,
                    "type": "column",
                    "column": col,
                    "semantic_role": semantic_role,
                    "entity_type": entity_type,
                },
            )
        )

    # Group columns by semantic role and entity types
    semantic_roles = defaultdict(list)
    entity_types = set()

    for col_name, col_data in data["columns"].items():

        # Handle backward compatibility for column structure
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

    # Add analytical capability document
    docs.append(
        Document(
            page_content=json.dumps({
                "time_columns": [c for c in semantic_roles.get("time", [])],
                "measure_columns": [c for c in semantic_roles.get("measure", [])],
                "entity_types": list(entity_types),
            }),
            metadata={
                "project_id": project_id,
                "table_name": table,
                "type": "analytical_capability",
            },
        )
    )

    # Add confidence note documents
    for note in data.get("confidence_notes", []):
        docs.append(
            Document(
                page_content=note,
                metadata={
                    "project_id": project_id,
                    "table_name": table,
                    "type": "confidence_note",
                },
            )
        )

    return docs