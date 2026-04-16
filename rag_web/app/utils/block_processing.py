import re


def normalize_visual_block(block):
    raw = block.get("content")

    if isinstance(raw, dict):
        return block

    if isinstance(raw, str) and "{{VISUAL" in raw:

        def extract(field):
            match = re.search(rf"{field}\s*:\s*(.*?);", raw, re.DOTALL)
            return match.group(1).strip().strip('"') if match else ""

        block["content"] = {
            "id": extract("id"),
            "type": extract("type"),
            "purpose": extract("purpose"),
        }

    return block


def build_prompt_blocks(blocks, decode_fn):
    formatted = []

    for i, block in enumerate(blocks):
        if block["type"] == "visual_placeholder":
            block = normalize_visual_block(block)

            content = block.get("content", {})

            decoded = decode_fn(
                block.get("generated_visual", {}).get("data")
            )

            formatted.append({
                "block_index": i,
                "type": "visual",
                "visual_id": content.get("id"),
                "visual_type": content.get("type"),
                "purpose": content.get("purpose"),
                "data": decoded
            })

        elif block["type"] in ["paragraph", "bullet_list"]:
            formatted.append({
                "block_index": i,
                "type": block["type"],
                "content": block["content"]
            })

    return formatted


def build_block_chunks(blocks, chunk_size=8):
    return [blocks[i:i + chunk_size] for i in range(0, len(blocks), chunk_size)]


def apply_repaired_blocks(original_blocks, repaired_blocks):
    for updated in repaired_blocks:
        idx = updated["block_index"]

        if idx >= len(original_blocks):
            continue

        if original_blocks[idx]["type"] not in ["paragraph", "bullet_list"]:
            continue

        original_blocks[idx]["content"] = updated["content"]

    return original_blocks