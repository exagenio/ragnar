def has_pending_visuals(content_obj):
    for section in content_obj.content_json.get("sections", []):
        for block in section.get("content_blocks", []):
            if block.get("type") == "visual_placeholder" and not block.get("generated_visual"):
                return True
    return False