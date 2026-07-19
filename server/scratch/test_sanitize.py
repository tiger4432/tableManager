import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone
import uuid
from database.crud import sanitize_to_utf8

def test_sanitize():
    now = datetime.now(timezone.utc)
    uid = uuid.uuid4()
    
    data = {
        "time": now,
        "uuid": uid,
        "nested": [now, uid, "hello"]
    }
    
    sanitized = sanitize_to_utf8(data)
    print("Sanitized data:", sanitized)
    
    assert isinstance(sanitized["time"], str)
    assert isinstance(sanitized["uuid"], str)
    assert isinstance(sanitized["nested"][0], str)
    assert isinstance(sanitized["nested"][1], str)
    print("All assertions passed successfully!")

if __name__ == "__main__":
    test_sanitize()
