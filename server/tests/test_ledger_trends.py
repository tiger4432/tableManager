"""Focused contract tests for the dynamic R&D Trend response."""
from datetime import datetime, timezone
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_api import finding_kinds  # noqa: E402
import ledger_trace_router  # noqa: E402
from ledger_api import ledger_trends  # noqa: E402
from ledger_api import ledger_identity  # noqa: E402


KINDS = {
    "alpha": {"label": "알파", "observed_by": ["a"],
              "observation_table": "alpha_obs", "extent_columns": ["x"],
              "classes": ["edge", "bulk"]},
    "beta": {"label": "베타", "observed_by": ["b"],
             "observation_table": "beta_obs", "extent_columns": ["x"],
             "classes": []},
}


@pytest.fixture(autouse=True)
def registry():
    finding_kinds.set_registry(KINDS)
    yield
    finding_kinds.set_registry(None)


def _now():
    return datetime(2026, 8, 14, 12, tzinfo=timezone.utc)


def test_wafer_leg_mark_is_collision_free_and_round_trips():
    left = ledger_identity.encode_mark("WF|A", "B")
    right = ledger_identity.encode_mark("WF", "A|B")
    assert left != right
    assert ledger_identity.decode_mark(left) == {"wafer": "WF|A", "bonding_leg": "B"}
    assert ledger_identity.decode_mark(right) == {"wafer": "WF", "bonding_leg": "A|B"}


def test_route_is_additive_and_registered_before_the_spa():
    paths = {route.path for route in ledger_trace_router.router.routes}
    assert "/api/ledger/trends" in paths


def test_variable_kind_and_subtype_series_share_exact_mark_keys(monkeypatch):
    monkeypatch.setattr(ledger_trends, "relation_exists", lambda *_: True)
    stamp = _now()
    series = [
        ("W A/1", "LEG-A", "alpha", None, stamp, 7, 3, 1, "found", 1, 1),
        ("W A/1", "LEG-A", "alpha", "edge", stamp, 4, 2, 1, "found", 1, 1),
        ("W A/1", "LEG-A", "alpha", "bulk", stamp, 3, 1, 1, "found", 1, 1),
        ("W A/1", "LEG-A", "beta", None, stamp, 2, 1, 1, "found", 1, 1),
    ]
    table = [
        ("W A/1", "LEG-A", stamp, "alpha", None, 7, 3, 1, "found"),
        ("W A/1", "LEG-A", stamp, "alpha", "edge", 4, 2, 1, "found"),
        ("W A/1", "LEG-A", stamp, "alpha", "bulk", 3, 1, 1, "found"),
        ("W A/1", "LEG-A", stamp, "beta", None, 2, 1, 1, "found"),
    ]
    trace = [("W A/1", "LEG-A", 2, 2, 1, ["core-1", "core-2"], ["dt-1"])]
    calls = iter((series, table, trace))
    monkeypatch.setattr(ledger_trends, "_fetch", lambda *_args, **_kw: next(calls))

    body = ledger_trends.trends(object(), now=_now())

    assert body["state"] == "ready"
    assert len(body["finding_kinds"]) == 2
    assert body["selectable_finding_kinds"] == body["finding_kinds"]
    assert body["applied_kinds"] == ["alpha", "beta"]
    assert all(kind["active"] and kind["selectable"]
               for kind in body["finding_kinds"])
    assert {s["id"] for s in body["series"]} == {
        "alpha:all", "alpha:edge", "alpha:bulk", "beta:all"}
    row_key = body["table"]["rows"][0]["identity"]["mark_key"]
    assert ledger_identity.decode_mark(row_key) == {
        "wafer": "W A/1", "bonding_leg": "LEG-A"}
    assert {p["identity"]["mark_key"] for s in body["series"]
            for p in s["points"]} == {row_key}
    assert body["composition"]["included"] is False
    assert [row["id"] for row in body["trace_dimensions"]] == [
        "dt_trace", "core_trace"]
    assert body["table"]["rows"][0]["traceability"] == {
        "dt": {"state": "partial", "count": 1, "component_denominator": 2,
               "evidence_ids": ["evidence:dt-1"]},
        "core": {"state": "ready", "count": 2, "component_denominator": 2,
                 "evidence_ids": ["evidence:core-1", "evidence:core-2"]},
    }
    assert body["finding_kinds"][0]["metrics"][2] == {
        "id": "found_rate", "label": "발생 칩비", "state": "ready",
        "numerator": "found_chip_count", "denominator": "scan_denominator"}


def test_scanned_clean_reference_is_explicit_zero_with_denominator(monkeypatch):
    monkeypatch.setattr(ledger_trends, "relation_exists", lambda *_: True)
    stamp = _now()
    series, table = [], []
    for index in range(12):
        wafer = f"SYN-CX-BW-{index + 1:03d}"
        found = 1 if index < 6 else 0
        state = "found" if found else "scanned_clean"
        series.append((wafer, "LEG-A", "alpha", None, stamp, found, found, 64, state,
                       index + 1, 12))
        table.append((wafer, "LEG-A", stamp, "alpha", None, found, found, 64, state))
    trace = [(f"SYN-CX-BW-{index + 1:03d}", "LEG-A", 12, 12, 10,
              [f"core-{index}-{component}" for component in range(12)],
              [f"dt-{index}-{component}" for component in range(10)])
             for index in range(12)]
    calls = iter((series, table, trace))
    monkeypatch.setattr(ledger_trends, "_fetch", lambda *_a, **_k: next(calls))
    body = ledger_trends.trends(object(), kinds="alpha", now=stamp)
    assert body["applied_kinds"] == ["alpha"]
    assert [row["id"] for row in body["selectable_finding_kinds"]] == ["alpha", "beta"]
    points = body["series"][0]["points"]
    assert len(points) == 12
    assert sum(p["value"]["state"] == "found" for p in points) == 6
    assert sum(p["value"]["state"] == "scanned_clean" for p in points) == 6
    clean = [p for p in points if p["value"]["state"] == "scanned_clean"]
    assert all(p["value"]["event_count"] == 0 for p in clean)
    assert all(p["value"]["found_chip_count"] == 0 for p in clean)
    assert all(p["value"]["scan_denominator"] == 64 for p in clean)
    assert all(p["value"]["found_rate"] == 0 for p in clean)
    assert len(body["table"]["rows"]) == 12
    assert all(row["traceability"]["core"]["state"] == "ready"
               for row in body["table"]["rows"])
    assert all(row["traceability"]["dt"]["state"] == "partial"
               for row in body["table"]["rows"])


def test_table_uses_keyset_cursor_and_limit_is_not_domain_cardinality(monkeypatch):
    monkeypatch.setattr(ledger_trends, "relation_exists", lambda *_: True)
    stamps = [datetime(2026, 8, 14, hour, tzinfo=timezone.utc) for hour in (11, 10, 9)]
    series = [(f"W-{i}", "LEG-A", "alpha", None, stamp, i, i, 1, "found", i, 3)
              for i, stamp in enumerate(stamps, 1)]
    table = [(f"W-{i}", "LEG-A", stamp, "alpha", None, i, i, 1, "found")
             for i, stamp in enumerate(stamps, 1)]
    calls = iter((series, table, []))
    monkeypatch.setattr(ledger_trends, "_fetch", lambda *_args, **_kw: next(calls))

    first = ledger_trends.trends(object(), kinds="alpha", limit=2, now=_now())
    assert first["table"]["returned"] == 2
    assert first["table"]["truncated"] is True
    assert first["table"]["next_cursor"]
    assert first["series"][0]["downsampling"]["input_wafer_count"] == 3
    assert all(row["traceability"]["dt"]["state"] == "absent"
               for row in first["table"]["rows"])

    decoded = ledger_trends._decode_cursor(first["table"]["next_cursor"])
    assert decoded == (stamps[1], "W-2", "LEG-A")


def test_absent_relation_keeps_declarations_and_never_queries(monkeypatch):
    monkeypatch.setattr(ledger_trends, "relation_exists", lambda *_: False)
    monkeypatch.setattr(ledger_trends, "_fetch",
                        lambda *_args, **_kw: pytest.fail("absent relation was queried"))
    body = ledger_trends.trends(object(), now=_now())
    assert body["state"] == "absent"
    assert [k["id"] for k in body["finding_kinds"]] == ["alpha", "beta"]
    assert body["applied_kinds"] == ["alpha", "beta"]
    assert body["series"] == []
    assert body["table"]["rows"] == []


@pytest.mark.parametrize("kwargs,reason", [
    ({"cursor": "not-base64"}, ledger_trends.REASON_BAD_CURSOR),
    ({"limit": 201}, ledger_trends.REASON_BAD_LIMIT),
    ({"max_points": 501}, ledger_trends.REASON_BAD_POINTS),
    ({"window": "1000d"}, ledger_trends.REASON_WINDOW_TOO_WIDE),
])
def test_malformed_or_unbounded_questions_are_refused_before_sql(monkeypatch,
                                                                  kwargs, reason):
    monkeypatch.setattr(ledger_trends, "_fetch",
                        lambda *_args, **_kw: pytest.fail("refusal happened after SQL"))
    with pytest.raises(ledger_trends.TrendRequestError) as caught:
        ledger_trends.trends(object(), now=_now(), **kwargs)
    assert caught.value.detail["reason"] == reason


def test_empty_or_inactive_kind_selection_is_refused_before_sql(monkeypatch):
    registry = {**KINDS, "disabled": {"label": "비활성", "active": False,
                                      "observed_by": ["d"],
                                      "observation_table": "disabled_obs",
                                      "extent_columns": ["x"], "classes": []}}
    finding_kinds.set_registry(registry)
    monkeypatch.setattr(ledger_trends, "_fetch",
                        lambda *_a, **_k: pytest.fail("refusal happened after SQL"))
    with pytest.raises(ledger_trends.TrendRequestError) as empty:
        ledger_trends.trends(object(), kinds=" , ", now=_now())
    assert empty.value.detail["reason"] == ledger_trends.REASON_EMPTY_KINDS
    with pytest.raises(ledger_trends.TrendRequestError) as inactive:
        ledger_trends.trends(object(), kinds="disabled", now=_now())
    assert inactive.value.detail["reason"] == ledger_trends.REASON_INACTIVE_KIND


def test_default_selection_uses_only_active_declarations(monkeypatch):
    registry = {**KINDS, "disabled": {"label": "비활성", "active": False,
                                      "observed_by": ["d"],
                                      "observation_table": "disabled_obs",
                                      "extent_columns": ["x"], "classes": []}}
    finding_kinds.set_registry(registry)
    monkeypatch.setattr(ledger_trends, "relation_exists", lambda *_: False)
    body = ledger_trends.trends(object(), now=_now())
    assert [row["id"] for row in body["selectable_finding_kinds"]] == [
        "alpha", "beta", "disabled"]
    assert body["applied_kinds"] == ["alpha", "beta"]
    assert body["selectable_finding_kinds"][2]["active"] is False


def test_sql_is_time_bounded_keyset_paged_and_database_downsampled():
    series_sql = ledger_trends._series_sql()
    table_sql = ledger_trends._table_sql(True)
    assert "occurred_at >= %(from)s" in series_sql
    assert "%(max_points)s" in series_sql
    assert "LIMIT %(page_size)s" in table_sql
    assert "(max(occurred_at), wafer, bonding_leg) <" in table_sql
    assert "OFFSET" not in table_sql.upper()
    trace_sql = ledger_trends._traceability_sql()
    assert "occurred_at >= %(from)s" in trace_sql
    assert "jsonb_to_recordset(%(page_units)s::jsonb)" in trace_sql
    assert "predicate = 'transferred'" in trace_sql
