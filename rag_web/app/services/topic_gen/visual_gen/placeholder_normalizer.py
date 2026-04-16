def normalize_placeholders(content_json: dict) -> dict:
    """Normalize placeholder formats"""

    sections = content_json.get("sections", [])

    for section in sections:
        blocks = section.get("content_blocks", [])

        for block in blocks:

            block_type = block.get("type")

            # Process only visual placeholders
            if block_type != "visual_placeholder":
                continue

            raw = block.get("content")

            # Handle string content
            if isinstance(raw, str):

                raw = raw.strip()

                # Skip if already formatted
                if raw.startswith("{{VISUAL"):
                    continue

                # Wrap json-like string
                if raw.startswith("{"):
                    cleaned = raw.strip("{} \n")

                    block["content"] = (
                        "{{VISUAL:\n"
                        f"{cleaned}\n"
                        "}}"
                    )

            # Handle dictionary content
            elif isinstance(raw, dict):

                # Convert dictionary into visual placeholder
                block["content"] = (
                    "{{VISUAL:\n"
                    f"  id: {raw.get('id')};\n"
                    f"  type: {raw.get('type')};\n"
                    f"  purpose: \"{raw.get('purpose')}\";\n"
                    "}}"
                )

    return content_json
