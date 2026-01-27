import re

def normalize_title(value: str) -> str:
    """
    Normalize titles so comparisons are stable across:
    - Outline JSON
    - DB
    - URLs
    """
    value = value.lower().strip()
    value = re.sub(r"[^\w\s]", "", value)   # remove punctuation
    value = re.sub(r"\s+", " ", value)      # normalize spaces
    return value
