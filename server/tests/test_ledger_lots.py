# -*- coding: utf-8 -*-
"""`GET /api/ledger/lots` — asserted on the RULES, not on the happy path.

These run WITHOUT PostgreSQL on purpose. Every rule below is a property of the envelope
and the cell arithmetic, and none of it needs a database — so unlike this project's
`*_pg.py` files these do not skip on a box with no `ASSY_PG_TEST_DATABASE_URL`, and a
green line here is a green line rather than a grey one. The SQL itself is exercised
against a live PostgreSQL in `test_ledger_lots_pg.py`.

WHAT EACH TEST DEFENDS
-----------------------
1. `test_the_provenance_seam_is_the_only_thing_that_moves` — the lead PM's explicit ask
   (2026-08-14): when the `observed` translation lands, the response says
   `ledger_backed: true` and THE CLIENT DOES NOT CHANGE A LINE. Asserted rather than
   hoped about.
2. `test_an_unscanned_cell_is_never_a_zero` / `test_a_scanned_cell_with_nothing_found_is_a_zero`
   — the two halves of 「미검사 ≠ 0」. Either one alone passes on a broken implementation:
   a module that returns `null` for everything passes the first, one that returns `0` for
   everything passes the second.
3. `test_extent_mean_divides_by_found_and_never_by_scanned` — averaging a zero in for
   every clean chip drags a lot's mean toward zero in proportion to how WELL it did.
4. `test_declaring_a_kind_adds_a_column_family_with_no_edit_here` — the owner's
   「지표 목록을 하드코딩하지 마십시오」, driven rather than asserted about the source text.
5. `test_an_unknown_kind_or_aggregate_is_refused_by_name` — a misspelled column must not
   silently render some other column's numbers under the misspelled heading.
6. `test_the_baseline_excludes_a_non_production_row_but_the_row_stays` — owner constraint
   2: 표시하되 구분. A filter that hides the row would delete the evidence.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import finding_kinds                                                # noqa: E402
import ledger_lots                                                  # noqa: E402
import ledger_siblings                                              # noqa: E402


# --------------------------------------------------------------------------- fixtures
#: A geometry and attribution named nothing like the live config, so a literal borrowed
#: from `siblings_axes.json` cannot satisfy any assertion here.
SWAPPED_AXES = {
    "geometry": {
        "unit": "widget", "unit_label": "위젯",
        "unit_columns": ["base_wafer_id", "base_x", "base_y"],
        "run_key_column": "run_uid", "run_method_column": "method",
        "run_time_column": "observed_at", "observation_run_ref_column": "run_uid",
        "universe": {"relation": "bonding_log",
                     "join": {"base_wafer_id": "base_id", "base_x": "bx",
                              "base_y": "by"}},
    },
    "attribution": [{
        "relation": "bonding_log", "about": "process", "label": "크레이트 공정",
        "join": {"base_wafer_id": "base_id", "base_x": "bx", "base_y": "by"},
        "axes": [{"name": "crate_lot", "label": "크레이트 랏", "column": "bond_lot"},
                 {"name": "crate_eqp", "label": "크레이트 장비", "column": "bond_eqp"}],
    }],
    "kinds": {},
}

SWAPPED_KINDS = {
    "bolt": {"label": "볼트", "observed_by": ["xray"], "observation_table": "void_obs",
             "extent_columns": ["radius_x", "radius_y"], "unit_column": "unit"},
    "crack": {"label": "크랙", "observed_by": [], "observation_table": "delam_obs",
              "extent_columns": ["extent_x", "extent_y"], "unit_column": "unit"},
}


@pytest.fixture
def declared():
    """Install the swapped declarations, and put the real ones back afterwards."""
    ledger_siblings.set_axes_config(SWAPPED_AXES)
    finding_kinds.set_registry(SWAPPED_KINDS)
    yield
    finding_kinds.set_registry(None)
    ledger_siblings.set_axes_config(None)


def _raw(row_value, scanned, found, events, extent, universe=100):
    """One row as `_run` hands it over — the alias shape, not the SQL."""
    return {"row_value": row_value, "universe": universe,
            "first_at": None, "last_at": None,
            "scanned_0": scanned, "found_0": found,
            "events_0": events, "extent_0": extent}


def _envelope(columns, rows, **kw):
    config = ledger_siblings.load_axes_config()
    kind = columns[0].kind
    source, axis = ledger_lots.resolve_row_axis(config, kind)
    from datetime import datetime, timezone
    window = ledger_siblings.parse_window(None)
    gate = {"total_bytes": 1, "max_bytes": 2, "relations": {}, "absent_relations": [],
            "forced": False, "reason": None}
    return ledger_lots._envelope(
        ledger_lots.STATE_READY, columns, axis, source, config, kind, rows,
        window, window, gate, ["bonding_log", "inspection_run"],
        datetime(2026, 8, 14, tzinfo=timezone.utc), **kw)


def _cell(body, row_value, column_id):
    row = next(r for r in body["rows"] if r["row"] == row_value)
    return next(c for c in row["cells"] if c["column"] == column_id)


# --------------------------------------------------------------------------- 1
def test_the_provenance_seam_is_the_only_thing_that_moves(declared, monkeypatch):
    """🔴 THE LEAD PM'S ASK, DRIVEN.

    Build the whole answer twice — once as it is served today (source tables), once as it
    will be served after the `observed` translation lands (ledger-backed) — and assert
    that NOTHING ELSE in the response differs. If a future change makes any other field
    depend on where the numbers came from, the client would have to branch on provenance
    and this fails.
    """
    columns = ledger_lots.parse_columns("bolt:found_rate,bolt:per_chip")
    rows = [_raw("L-1", 100, 40, 55, 3.0), _raw("L-2", 100, 10, 12, 2.0)]

    today = _envelope(columns, rows)
    assert today["provenance"]["ledger_backed"] is False
    assert today["provenance"]["source"] == ledger_lots.PROVENANCE_SOURCE_TABLES

    def ledger_backed(relations, gate):
        return {"source": ledger_lots.PROVENANCE_LEDGER, "ledger_backed": True,
                "relations": ["ledger_events"], "absent_relations": [],
                "note": "번역 착지"}

    monkeypatch.setattr(ledger_lots, "_provenance", ledger_backed)
    columns_again = ledger_lots.parse_columns("bolt:found_rate,bolt:per_chip")
    tomorrow = _envelope(columns_again, rows)

    assert tomorrow["provenance"]["ledger_backed"] is True
    assert tomorrow["provenance"] != today["provenance"], (
        "the mutation did not change provenance — this test would pass on anything")

    moved = {k for k in set(today) | set(tomorrow) if today.get(k) != tomorrow.get(k)}
    assert moved == {"provenance"}, (
        f"the translation must move `provenance` and NOTHING else; also moved: "
        f"{sorted(moved - {'provenance'})}")


# --------------------------------------------------------------------------- 2a
def test_an_unscanned_cell_is_never_a_zero(declared):
    """A row nobody scanned renders 「—」. It is not clean, not zero, not in the baseline.

    MEASURED motivation (`assy_manager`, 2026-08-14): a lot holds 3,525 chips and 725 are
    scanned. A client dividing by the lot size is wrong by 5x; a lot with no scan at all
    would render as a flawless 0.0% and sit at the BOTTOM of a surprise-ordered table.
    """
    columns = ledger_lots.parse_columns("bolt:found_rate")
    body = _envelope(columns, [_raw("L-scanned", 100, 0, 0, None),
                               _raw("L-never", 0, 0, None, None)])

    never = _cell(body, "L-never", "bolt:found_rate")
    assert never["state"] == ledger_lots.CELL_UNSCANNED
    assert never["value"] is None, "an unscanned cell must not carry a number"
    assert never["of"] == 0
    assert never["level"] is None, "an unscanned cell must not be coloured"
    assert never["ratio_to_baseline"] is None


# --------------------------------------------------------------------------- 2b
def test_a_scanned_cell_with_nothing_found_is_a_zero(declared):
    """The other half. `0` means LOOKED AT AND NOTHING FOUND and must render as 「0」.

    Without this, an implementation that answers `null` for everything passes the
    unscanned test above and says nothing true.
    """
    columns = ledger_lots.parse_columns("bolt:found_rate")
    body = _envelope(columns, [_raw("L-clean", 100, 0, 0, None),
                               _raw("L-bad", 100, 50, 60, 1.0)])

    clean = _cell(body, "L-clean", "bolt:found_rate")
    assert clean["state"] == ledger_lots.CELL_MEASURED
    assert clean["value"] == 0
    assert clean["of"] == 100, "a measured zero must still carry its denominator"


# --------------------------------------------------------------------------- 2c
def test_a_kind_with_no_methods_has_no_denominator_and_says_so(declared):
    """`crack` declares `observed_by: []` — an incidental observation nobody scans for.

    The honest answer is 「분모 없음 — 대조 불가」 as CONTENT, never a rate computed over
    whatever rows happened to be nearby.
    """
    columns = ledger_lots.parse_columns("crack:found_rate")
    body = _envelope(columns, [{"row_value": "L-1", "universe": 10, "first_at": None,
                                "last_at": None, "scanned_0": 0, "found_0": 3,
                                "events_0": 3, "extent_0": 1.0}])
    cell = _cell(body, "L-1", "crack:found_rate")
    assert cell["state"] == ledger_lots.CELL_NO_DENOMINATOR
    assert cell["value"] is None
    assert body["columns"][0]["has_denominator"] is False
    assert body["columns"][0]["denominator"] is None


# --------------------------------------------------------------------------- 3
def test_extent_mean_divides_by_found_and_never_by_scanned(declared):
    """A chip with no bolt has no bolt SIZE — it is a missing value, not a zero.

    Dividing the mean size by `scanned` would drag every lot's average toward zero in
    proportion to how WELL that lot did, so the cleanest lot would look like it had the
    smallest defects. `of` must therefore report `found`.
    """
    columns = ledger_lots.parse_columns("bolt:extent_mean")
    body = _envelope(columns, [_raw("L-1", 1000, 10, 10, 50.0)])
    cell = _cell(body, "L-1", "bolt:extent_mean")
    assert cell["state"] == ledger_lots.CELL_MEASURED
    assert cell["value"] == 50.0
    assert cell["of"] == 10, "extent_mean's denominator is FOUND, not SCANNED"
    assert cell["of"] != 1000

    header = body["columns"][0]
    assert header["denominator"]["population"] == "found_chips"


def test_extent_mean_with_nothing_found_is_a_dash_not_a_zero(declared):
    """No finding means no size to average. Zero would be a measurement nobody took."""
    columns = ledger_lots.parse_columns("bolt:extent_mean")
    body = _envelope(columns, [_raw("L-1", 1000, 0, 0, None)])
    cell = _cell(body, "L-1", "bolt:extent_mean")
    assert cell["state"] == ledger_lots.CELL_UNSCANNED
    assert cell["value"] is None


# --------------------------------------------------------------------------- 4
def test_declaring_a_kind_adds_a_column_family_with_no_edit_here(declared):
    """🔴 THE OWNER'S RULE, DRIVEN RATHER THAN GREPPED.

    `default_columns()` is generated from the registry, so registering a third kind must
    widen the default table by itself. A hardcoded list passes every other test in this
    file on the day it is written.
    """
    before = {c.id for c in ledger_lots.default_columns()}
    assert any(c.startswith("bolt:") for c in before)
    assert not any(c.startswith("rivet:") for c in before)

    registry = dict(SWAPPED_KINDS)
    registry["rivet"] = {"label": "리벳", "observed_by": ["ct"],
                         "observation_table": "void_obs",
                         "extent_columns": ["radius_x"], "unit_column": "unit"}
    finding_kinds.set_registry(registry)
    after = {c.id for c in ledger_lots.default_columns()}

    assert after - before == {"rivet:found_rate", "rivet:per_chip"}, (
        "declaring a kind must add its column family with no code change here")


def test_every_declared_aggregate_applies_to_every_declared_kind(declared):
    """A metric is the CROSS PRODUCT of two declarations. Neither half may special-case
    the other — a `if kind == ...` in an aggregate would break exactly this."""
    for kind in finding_kinds.kinds():
        for aggregate in ledger_lots.aggregates():
            column = ledger_lots.Column(kind, aggregate)
            assert column.id == f"{kind}:{aggregate}"
            assert column.as_dict(None, [])["aggregate_label"]


# --------------------------------------------------------------------------- 5
def test_an_unknown_kind_or_aggregate_is_refused_by_name(declared):
    """Never defaulted. A misspelled kind in a URL that silently rendered the default
    kind's numbers would make every figure on the screen true of something else."""
    with pytest.raises(ledger_lots.LotGridRequestError) as unknown_kind:
        ledger_lots.parse_columns("bolttt:found_rate")
    assert unknown_kind.value.detail["reason"] == ledger_lots.REASON_UNKNOWN_KIND

    with pytest.raises(ledger_lots.LotGridRequestError) as unknown_agg:
        ledger_lots.parse_columns("bolt:median_rate")
    detail = unknown_agg.value.detail
    assert detail["reason"] == ledger_lots.REASON_UNKNOWN_AGGREGATE
    assert "found_rate" in detail["declared"], (
        "a refusal must name what IS declared, or the operator has to guess")

    with pytest.raises(ledger_lots.LotGridRequestError) as malformed:
        ledger_lots.parse_columns("bolt")
    assert malformed.value.detail["reason"] == ledger_lots.REASON_BAD_COLUMNS


def test_an_unknown_row_axis_is_refused_and_names_the_declared_ones(declared):
    config = ledger_siblings.load_axes_config()
    with pytest.raises(ledger_lots.LotGridRequestError) as exc:
        ledger_lots.resolve_row_axis(config, "bolt", "core_lot")
    assert exc.value.detail["reason"] == ledger_lots.REASON_UNKNOWN_AXIS
    assert "crate_lot" in exc.value.detail["declared"]


def test_the_default_row_axis_comes_from_the_declaration(declared):
    """🔴 NOT a lot column chosen in code. The swapped config names its lot axis
    `crate_lot`, and the default must follow the declaration to it."""
    config = ledger_siblings.load_axes_config()
    _source, axis = ledger_lots.resolve_row_axis(config, "bolt")
    assert axis.name == "crate_lot"
    assert axis.label == "크레이트 랏"


def test_the_row_axis_label_reaches_the_response(declared):
    """The lead PM's ruling: the screen must SAY which axis it is, so nobody reads a
    bonding lot as a core lot."""
    columns = ledger_lots.parse_columns("bolt:found_rate")
    body = _envelope(columns, [_raw("L-1", 10, 1, 1, 1.0)])
    assert body["row_axis"]["label"] == "크레이트 랏"
    assert body["row_axis"]["source"] == "bonding_log.bond_lot"
    assert {a["name"] for a in body["axes_available"]} == {"crate_lot", "crate_eqp"}


# --------------------------------------------------------------------------- 6
def test_the_baseline_is_the_median_and_the_level_is_served(declared):
    """The client never divides: it cannot know the baseline's exclusions."""
    columns = ledger_lots.parse_columns("bolt:found_rate")
    rows = [_raw(f"L-{i}", 100, 10, 10, 1.0) for i in range(4)]
    rows.append(_raw("L-hot", 100, 70, 70, 1.0))
    body = _envelope(columns, rows)

    assert body["columns"][0]["baseline"]["value"] == 0.1
    assert body["columns"][0]["baseline"]["basis"] == ledger_lots.BASELINE_MEDIAN_OF_ROWS

    hot = _cell(body, "L-hot", "bolt:found_rate")
    assert hot["ratio_to_baseline"] == 7.0
    assert hot["level"] == 4, "7x the baseline is past the top declared step"

    calm = _cell(body, "L-0", "bolt:found_rate")
    assert calm["level"] == 0, "a row at the baseline is not coloured"


def test_a_zero_baseline_yields_no_ratio_rather_than_an_infinity(declared):
    """「기저가 0이라 배수가 없다」 is a real answer; `inf` is not a number a screen
    can paint and `0` would say the opposite of what happened."""
    columns = ledger_lots.parse_columns("bolt:found_rate")
    body = _envelope(columns, [_raw("L-1", 100, 0, 0, None),
                               _raw("L-2", 100, 5, 5, 1.0)])
    assert body["columns"][0]["baseline"]["value"] == 0.025
    body_all_clean = _envelope(ledger_lots.parse_columns("bolt:found_rate"),
                               [_raw("L-1", 100, 0, 0, None),
                                _raw("L-2", 100, 0, 0, None)])
    assert body_all_clean["columns"][0]["baseline"]["value"] == 0
    for row in body_all_clean["rows"]:
        assert row["cells"][0]["ratio_to_baseline"] is None
        assert row["cells"][0]["level"] is None


def test_a_non_production_row_stays_on_the_screen(declared):
    """Owner constraint 2: 표시하되 구분. Until the special-evaluation discriminator is
    declared every row is `unknown` and counts — excluding on a guess would quietly
    reshape every colour, and a FILTER would delete the evidence entirely."""
    columns = ledger_lots.parse_columns("bolt:found_rate")
    body = _envelope(columns, [_raw("L-1", 100, 10, 10, 1.0)])
    bucket = body["rows"][0]["bucket"]
    assert bucket["id"] == "unknown"
    assert bucket["counts_toward_baseline"] is True
    assert "counts_toward_baseline" in bucket, (
        "the client must be TOLD whether a row counts, never infer it from the label")


# --------------------------------------------------------------------------- envelope
def test_no_cell_ships_a_ratio_without_its_denominator(declared):
    """The brief's standing rule (「모든 비율은 분모와 함께」), asserted over every
    declared aggregate at once rather than one example."""
    columns = [ledger_lots.Column("bolt", a) for a in ledger_lots.aggregates()]
    body = _envelope(columns, [_raw("L-1", 100, 25, 40, 7.5)])
    for cell in body["rows"][0]["cells"]:
        spec = ledger_lots.AGGREGATES[cell["column"].split(":")[1]]
        if cell["state"] != ledger_lots.CELL_MEASURED or spec["over"] is None:
            continue
        assert cell["of"] is not None, f"{cell['column']} shipped a ratio with no denominator"
        assert cell["n"] is not None


def test_the_internal_baseline_marker_never_reaches_the_client(declared):
    """`_counts` is scaffolding for the baseline pass. A leaked private field becomes a
    field somebody depends on."""
    columns = ledger_lots.parse_columns("bolt:found_rate,bolt:per_chip")
    body = _envelope(columns, [_raw("L-1", 100, 10, 10, 1.0)])
    for row in body["rows"]:
        for cell in row["cells"]:
            assert "_counts" not in cell


def test_paging_reports_what_was_truncated(declared):
    columns = ledger_lots.parse_columns("bolt:found_rate")
    rows = [_raw(f"L-{i}", 100, i, i, 1.0) for i in range(10)]
    body = _envelope(columns, rows, limit=3)
    assert body["populations"] == {"rows_total": 10, "rows_returned": 3,
                                   "rows_truncated": True}
    assert len(body["rows"]) == 3
