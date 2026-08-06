"""GET /tables/{t}/data serializes without FastAPI's `jsonable_encoder` pass.

Why this file exists, in one measurement: on the development database, over all 14
declared tables, `jsonable_encoder` cost 1,831 ms against 129 ms for a direct
`json.dumps` - and produced byte-identical output every time. On `dt_log` (1,000 rows /
4.4 MB) that was 548 ms of a 763 ms request, against 5.4 ms of actual SQL execution.
The encoder was converting an already-JSON-native dict into an identical one.

So this is not a tradeoff, it is waste - and that is exactly why it needs a test rather
than a benchmark. Two things must stay true, and each is one revert away from being
false:

  1. The bytes on the wire do not change. `test_bytes_are_identical_*` is what lets
     someone verify that claim without trusting this docstring.
  2. The encoder is actually skipped. Byte-identity alone would still pass if a future
     edit routed the payload back through `jsonable_encoder` - the output would be the
     same and the cost would silently return. `test_encoder_is_not_called_*` fails in
     that case, and it is the only test here that pins the performance property.

And the risk the fast path introduces: `json.dumps` raises on Decimal/datetime/UUID
where `jsonable_encoder` copes. Measured absent across all 14 tables today, but a new
column type is one config change away, and this route is the operator's main screen.
`test_non_native_*` drives that branch with values the schema could plausibly produce
and asserts the request still succeeds with today's bytes.
"""
import datetime
import decimal
import json
import uuid

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

import main


def _cell(value, **over):
    """A cell in the shape the grid contract actually ships - all seven keys.

    Not three. The boundary contract names `{value, is_overwrite, priority_source}`, but
    `fetch_and_merge_metadata` emits four more, and trimming them was explicitly NOT
    approved (client2 reads every one of them). Building the fixture at the real width
    keeps this test honest about what is being serialized.
    """
    cell = {
        "value": value,
        "is_overwrite": False,
        "is_collision_merge": False,
        "sources": {},
        "updated_by": "system",
        "manual_priority_source": None,
        "priority_source": None,
    }
    cell.update(over)
    return cell


def _payload(rows=25, cell_value=lambda i, c: f"v{i}-{c}"):
    """A payload shaped like the real route's return value."""
    return {
        "table_name": "dt_log",
        "total": 8995,
        "skip": 0,
        "limit": len(range(rows)),
        "data": [
            {
                "row_id": f"019fbdeb-68dc-7909-b9fa-{i:012d}",
                "table_name": "dt_log",
                "created_at": "2026-08-06 09:00:00",
                "updated_at": "2026-08-06 09:30:00",
                "data": {f"col_{c}": _cell(cell_value(i, c)) for c in range(8)},
            }
            for i in range(rows)
        ],
        "calculated_skip": None,
        "target_offset": -1,
    }


def _todays_bytes(payload):
    """Exactly what this route produced before the change: encoder, then JSONResponse.

    This is the oracle. It is deliberately written as the OLD path rather than as a
    hand-rolled `json.dumps(...)` with matching kwargs - a hand-rolled copy would drift
    from Starlette's serializer settings and start asserting its own assumptions.
    """
    return JSONResponse(content=jsonable_encoder(payload)).body


# ─────────────────────────── 1. the bytes do not change ───────────────────────────

def test_bytes_are_identical_for_a_native_payload():
    payload = _payload()
    assert main._table_data_response(payload, "dt_log").body == _todays_bytes(payload)


@pytest.mark.parametrize("value", [
    "plain",
    "",
    None,
    True,
    False,
    0,
    -17,
    3.5,
    "unicode 한글 · 漢字 · emoji 🧿",     # ensure_ascii=False territory
    "quote\" backslash\\ newline\n tab\t",
    "</script><!--",                      # nothing HTML-escapes these on either path
])
def test_bytes_are_identical_per_value_type(value):
    """Per-value rather than one big fixture: a single differing encoding would
    otherwise hide inside a 4 MB blob and the diff would be unreadable."""
    payload = _payload(rows=2, cell_value=lambda i, c: value)
    assert main._table_data_response(payload, "dt_log").body == _todays_bytes(payload)


def test_empty_result_is_identical():
    payload = {"total": 0, "data": [], "skip": 0, "limit": 100,
               "calculated_skip": 0, "target_offset": -1}
    assert main._table_data_response(payload, "dt_log").body == _todays_bytes(payload)


def test_response_is_json_with_the_expected_media_type():
    """The route returns a Response now, so the content type is ours to get wrong."""
    resp = main._table_data_response(_payload(rows=2), "dt_log")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert json.loads(resp.body)["table_name"] == "dt_log"


# ──────────────── 2. the encoder is actually skipped (the perf pin) ────────────────

def test_encoder_is_not_called_for_a_native_payload(monkeypatch):
    """The only test here that fails if the optimization is reverted.

    Byte-identity would still hold if someone re-routed this through the encoder, so
    without this test the suite would stay green while the 548 ms came back.
    """
    calls = []
    monkeypatch.setattr(main, "jsonable_encoder",
                        lambda *a, **k: calls.append(1) or jsonable_encoder(*a, **k))
    main._table_data_response(_payload(), "dt_log")
    assert calls == [], "jsonable_encoder ran on a payload that is already JSON-native"


def test_native_payload_does_not_count_a_fallback():
    main.SLOW_JSON_FALLBACKS.pop("counter_probe", None)
    main._table_data_response(_payload(), "counter_probe")
    assert "counter_probe" not in main.SLOW_JSON_FALLBACKS


# ─────────── 3. the day the payload stops being native, it degrades ───────────

@pytest.mark.parametrize("odd", [
    decimal.Decimal("12.34"),                                  # a numeric column type
    datetime.datetime(2026, 8, 6, 9, 30, 0),                   # an unformatted timestamp
    datetime.date(2026, 8, 6),                                 # a date column
    uuid.UUID("019fbdeb-68dc-7909-b9fa-1e37a64e9c41"),         # a raw key
])
def test_non_native_value_falls_back_and_still_serves(odd, caplog):
    """`json.dumps` raises on these; `jsonable_encoder` does not. The request must
    survive, and must survive with TODAY's bytes - not with some other encoding."""
    payload = _payload(rows=3)
    payload["data"][1]["data"]["col_3"]["value"] = odd
    key = f"fallback_probe_{type(odd).__name__}"
    main.SLOW_JSON_FALLBACKS.pop(key, None)

    with caplog.at_level("WARNING"):
        resp = main._table_data_response(payload, key)

    assert resp.status_code == 200
    assert resp.body == _todays_bytes(payload), "fallback changed the bytes on the wire"
    assert main.SLOW_JSON_FALLBACKS[key] == 1, "fallback was not counted"
    # `getMessage()` applies the lazy %-args exactly once. `record.message` is only
    # populated once a formatter has run, and interpolating it again double-formats.
    warned = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("NOT JSON-native" in m for m in warned), f"fallback was silent: {warned}"
    assert any(key in m for m in warned), "the warning does not name the table"


def test_fallback_counter_accumulates_per_table():
    """A slow path nobody notices is how this gets un-fixed, so the count has to grow."""
    payload = _payload(rows=1)
    payload["data"][0]["data"]["col_0"]["value"] = decimal.Decimal("1")
    main.SLOW_JSON_FALLBACKS.pop("accum_probe", None)
    for _ in range(3):
        main._table_data_response(payload, "accum_probe")
    assert main.SLOW_JSON_FALLBACKS["accum_probe"] == 3


def test_nan_still_fails_exactly_as_it_does_today():
    """NaN raises under `allow_nan=False` on BOTH paths - the encoder cannot rescue it.

    Pinned because the fallback catches ValueError as well as TypeError, and the point
    of catching it is that the outcome stays identical to today rather than becoming a
    different failure on the way to the encoder.
    """
    payload = _payload(rows=1)
    payload["data"][0]["data"]["col_0"]["value"] = float("nan")
    with pytest.raises(ValueError):
        _todays_bytes(payload)                      # today
    with pytest.raises(ValueError):
        main._table_data_response(payload, "nan_probe")   # and after the change


# ───────────────────────── 4. the route still works end to end ─────────────────────

def test_route_returns_valid_json_through_the_real_stack(client):
    """FastAPI must hand our Response through untouched - status, body and header."""
    resp = client.get("/tables/inventory_master/data?skip=0&limit=10")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["table_name"] == "inventory_master"
    for field in ("total", "data", "skip", "limit", "target_offset"):
        assert field in body, f"response lost the '{field}' field the client reads"


def test_route_fast_fail_exit_also_returns_json(client):
    """The `target_row_id` miss is the route's OTHER exit and returns its own payload."""
    resp = client.get("/tables/inventory_master/data?target_row_id=does-not-exist")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["target_offset"] == -1
