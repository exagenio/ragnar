import base64
import struct


def stringify_blocks(blocks):
    """Convert content blocks into plain text for evaluation."""

    lines = []

    for block in blocks:
        if block["type"] == "paragraph":
            lines.append(block["content"])

        elif block["type"] == "bullet_list":
            for item in block["content"]:
                lines.append(f"- {item}")

        elif block["type"] == "visual":
            lines.append(
                f"[VISUAL]\n"
                f"Type: {block.get('visual_type')}\n"
                f"Purpose: {block.get('purpose')}\n"
            )

    return "\n\n".join(lines)


def extract_content_blocks_text(content_json):
    """Extract report topic content blocks as text for GEval."""

    sections = content_json.get("sections", [])
    all_blocks = []

    for section in sections:
        all_blocks.extend(section.get("content_blocks", []))

    formatted = build_prompt_blocks(all_blocks, _decode_sql_result)

    return stringify_blocks(formatted)


def decode_bdata(bdata, dtype):
    """Decode binary data from Plotly/SQL result payloads."""

    binary = base64.b64decode(bdata)

    if dtype == "f8":
        return list(struct.unpack(f"{len(binary)//8}d", binary))
    if dtype == "f4":
        return list(struct.unpack(f"{len(binary)//4}f", binary))
    if dtype == "i4":
        return list(struct.unpack(f"{len(binary)//4}i", binary))
    if dtype == "i2":
        return list(struct.unpack(f"{len(binary)//2}h", binary))
    if dtype == "i1":
        return list(struct.unpack(f"{len(binary)}b", binary))

    return []


def _decode_sql_result(sql_result):
    """Decode SQL result objects embedded in generated visual blocks."""

    if not sql_result:
        return sql_result

    if isinstance(sql_result, dict) and "rows" in sql_result:
        return sql_result

    if isinstance(sql_result, dict):
        decoded = {}

        for key, val in sql_result.items():
            if isinstance(val, dict) and "bdata" in val:
                decoded[key] = decode_bdata(val["bdata"], val.get("dtype"))
            else:
                decoded[key] = val

        return decoded

    return sql_result


def build_prompt_blocks(blocks, decode_fn):
    """Normalize topic content blocks into prompt-ready text blocks."""

    formatted = []

    for index, block in enumerate(blocks):
        if block["type"] == "visual_placeholder":
            block = normalize_visual_block(block)

            content = block.get("content", {})
            decoded = decode_fn(block.get("generated_visual", {}).get("data"))

            formatted.append(
                {
                    "block_index": index,
                    "type": "visual",
                    "visual_id": content.get("id"),
                    "visual_type": content.get("type"),
                    "purpose": content.get("purpose"),
                    "data": decoded,
                }
            )

        elif block["type"] in ["paragraph", "bullet_list"]:
            formatted.append(
                {
                    "block_index": index,
                    "type": block["type"],
                    "content": block["content"],
                }
            )

    return formatted


def normalize_visual_block(block):
    """Normalize string visual placeholders into structured visual metadata."""

    raw = block.get("content")

    if isinstance(raw, dict):
        return block

    if isinstance(raw, str) and "{{VISUAL" in raw:
        import re

        def extract(field):
            match = re.search(rf"{field}\s*:\s*(.*?);", raw, re.DOTALL)
            return match.group(1).strip().strip('"') if match else ""

        block["content"] = {
            "id": extract("id"),
            "type": extract("type"),
            "purpose": extract("purpose"),
        }

    return block
