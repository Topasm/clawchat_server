import json
import uuid


def make_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def serialize_tags(tags: list[str] | None) -> str | None:
    """Convert a list of tags to JSON string for storage."""
    return json.dumps(tags) if tags else None


def deserialize_tags(raw: str | None) -> list[str]:
    """Convert a JSON string of tags to a list."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def apply_model_updates(
    db_model, updates, tag_fields: set[str] = {"tags"}, timestamp=None
):
    """Apply updates from a Pydantic schema or dict to a SQLAlchemy model, handling tag serialization."""
    from datetime import datetime, timezone

    if hasattr(updates, "model_dump"):
        update_dict = updates.model_dump(exclude_unset=True)
    elif hasattr(updates, "dict"):
        update_dict = updates.dict(exclude_unset=True)
    else:
        update_dict = updates

    for field, value in update_dict.items():
        if field in tag_fields:
            value = serialize_tags(value)
        setattr(db_model, field, value)

    if timestamp is not None:
        db_model.updated_at = timestamp
    elif hasattr(db_model, "updated_at"):
        db_model.updated_at = datetime.now(timezone.utc)


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from text."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()
