import json
from typing import Any, Dict

def get_payload_dict(val: Any) -> Dict[str, Any]:
    """
    Safely converts an event, DatabaseOutbox model instance, or payload (dict or JSON string)
    into a Python dictionary. Guarantees a valid dict is returned, preventing
    'str' object has no attribute 'get' runtime errors.
    """
    if val is None:
        return {}
    
    # Check if object has pre-parsed payload attribute
    if hasattr(val, "_parsed_payload") and isinstance(val._parsed_payload, dict):
        return val._parsed_payload
    
    # Check if object has safe_payload property
    if hasattr(val, "safe_payload") and isinstance(val.safe_payload, dict):
        return val.safe_payload
    
    # Extract payload if passed a model instance or event dict with 'payload'
    if hasattr(val, "payload"):
        val = val.payload
    elif isinstance(val, dict) and "payload" in val and len(val) == 1:
        val = val["payload"]
        
    if isinstance(val, dict):
        return val
        
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
            
    return {}
