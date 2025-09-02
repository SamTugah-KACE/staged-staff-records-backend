from uuid import UUID
from datetime import datetime



def serialize_for_json(data):
    """
    Converts non-serializable data (like UUIDs) into JSON-compatible types.
    """
    if isinstance(data, dict):
        return {key: serialize_for_json(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [serialize_for_json(item) for item in data]
    elif isinstance(data, UUID):
        return str(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    return data