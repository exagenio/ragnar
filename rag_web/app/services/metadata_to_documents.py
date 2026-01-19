from langchain_core.documents import Document



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
    for col, desc in data["columns"].items():
        docs.append(
            Document(
                page_content=desc,
                metadata={
                    "project_id": project_id,
                    "table_name": table,
                    "type": "column",
                    "column": col,
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
