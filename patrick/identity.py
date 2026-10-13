"""Render the selected assistant name without changing stored source documents."""
import re


def render_identity(text, name="patrick"):
    name = name.strip().title()
    if not name:
        raise ValueError("Assistant name cannot be empty.")
    text = text.replace("{assistant_name}", name)
    # Backward compatibility for older prompts and assistant references in RAG.
    return re.sub(r"\bPatrick\b", lambda match: name, text, flags=re.I)
