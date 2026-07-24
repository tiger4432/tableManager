import pytest
import json
from unittest.mock import MagicMock
from database.models import DatabaseOutbox
from utils.payload_helper import get_payload_dict
from chain_ingestion_worker import process_chain_transaction_group, execute_custom_mapper

def test_get_payload_dict_various_inputs():
    # 1. Plain dictionary
    d = {"key": "value"}
    assert get_payload_dict(d) == {"key": "value"}

    # 2. JSON String
    s = json.dumps({"source_name": "user", "transaction_id": "tx_123"})
    assert get_payload_dict(s) == {"source_name": "user", "transaction_id": "tx_123"}

    # 3. Malformed JSON String or Non-JSON string
    assert get_payload_dict("not_a_json_string") == {}

    # 4. None / Empty
    assert get_payload_dict(None) == {}
    assert get_payload_dict({}) == {}

    # 5. DatabaseOutbox object with string payload
    outbox_str = DatabaseOutbox(
        event_uuid="uuid_1",
        event_type="CREATE",
        table_name="test_table",
        payload=json.dumps({"source_name": "user", "transaction_id": "tx_456"})
    )
    assert get_payload_dict(outbox_str) == {"source_name": "user", "transaction_id": "tx_456"}

    # 6. DatabaseOutbox object with _parsed_payload
    outbox_parsed = DatabaseOutbox(
        event_uuid="uuid_2",
        event_type="CREATE",
        table_name="test_table",
        payload=json.dumps({"source_name": "user"})
    )
def dummy_mapper(db, payload):
    assert isinstance(payload, dict)
    assert payload.get("source_name") == "user"
    return {"updates": []}

@pytest.mark.anyio
async def test_process_chain_transaction_group_with_string_payload():
    """
    Verifies process_chain_transaction_group does NOT crash with 'str' object has no attribute 'get'
    when DatabaseOutbox event payload is a raw JSON string.
    """
    mock_db = MagicMock()
    
    # Event whose payload is a JSON string instead of dict
    raw_payload_str = json.dumps({
        "source_name": "user",
        "transaction_id": "tx_str_test",
        "data": {"col1": "val1"}
    })
    
    event = DatabaseOutbox(
        event_uuid="uuid_str_1",
        event_type="CREATE",
        table_name="trigger_table",
        payload=raw_payload_str
    )
    
    # Simple rule matching trigger_table pointing to dummy_mapper
    rules = [
        {
            "name": "test_rule",
            "trigger_table": "trigger_table",
            "target_table": "target_table",
            "mapper_module": "tests.test_chain_payload_resilience",
            "mapper_function": "dummy_mapper",
            "enabled": True,
            "is_batch": False
        }
    ]
    
    # Execute transaction group processing
    success, error, broadcast_messages = await process_chain_transaction_group("tx_str_test", [event], mock_db, rules)
    assert success is True
    assert error is None
    # 통지 메시지는 커밋 이후 호출부에서 fire-and-forget으로 발사되며, 반환은 리스트여야 한다.
    assert isinstance(broadcast_messages, list)
