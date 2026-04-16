import json
from langchain_core.documents import Document
from collections import defaultdict


def metadata_to_documents(metadata_obj):
    docs = []
    data = metadata_obj.approved_metadata

    project_id = metadata_obj.project.id
    table = metadata_obj.table_name

    # Table description
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

    # Column descriptions
    for col, col_data in data["columns"].items():

        # 🔹 Backward compatibility
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

    semantic_roles = defaultdict(list)
    entity_types = set()

    for col_name, col_data in data["columns"].items():

        # 🔹 Backward compatibility
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


    # Confidence notes
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
