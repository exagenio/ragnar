def normalize_placeholders(content_json: dict) -> dict:
    """
    Normalize malformed SQL / VISUAL placeholders produced by the LLM.
    Converts dict placeholders into proper {{SQL_CALCULATION}} / {{VISUAL}} format.
    """

    sections = content_json.get("sections", [])

    for section in sections:
        blocks = section.get("content_blocks", [])

        for block in blocks:

            block_type = block.get("type")

            if block_type != "visual_placeholder":
                continue

            raw = block.get("content")

            # --------------------------------
            # CASE 1 — Already correct string
            # --------------------------------
            if isinstance(raw, str):

                raw = raw.strip()

                if block_type == "sql_placeholder" and raw.startswith("{{SQL_CALCULATION"):
                    continue

                if block_type == "visual_placeholder" and raw.startswith("{{VISUAL"):
                    continue

                # If string but missing wrapper
                if raw.startswith("{"):

                    cleaned = raw.strip("{} \n")

                    if block_type == "sql_placeholder":
                        block["content"] = (
                            "{{SQL_CALCULATION:\n"
                            f"{cleaned}\n"
                            "}}"
                        )

                    else:
                        block["content"] = (
                            "{{VISUAL:\n"
                            f"{cleaned}\n"
                            "}}"
                        )

            # --------------------------------
            # CASE 2 — Content is a dict (LLM parsed JSON)
            # --------------------------------
            elif isinstance(raw, dict):
                if block_type == "visual_placeholder":

                    block["content"] = (
                        "{{VISUAL:\n"
                        f"  id: {raw.get('id')};\n"
                        f"  type: {raw.get('type')};\n"
                        f"  purpose: \"{raw.get('purpose')}\";\n"
                        "}}"
                    )

    return content_json