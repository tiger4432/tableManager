# -*- coding: utf-8 -*-
"""파생행이 그 그룹의 «집계»를 싣고, 참조뷰가 그것으로 조회한다 (S-129, 판정 16:05).

🔴 THE CASE. One lot's bonding log arrives in several transactions and every row carries a
different time. What a reference view wants to ask with is the lot group's EARLIEST bonding
time - a fact about the group, not about any row in it.

⛔ AND IT MUST NOT BE PART OF THE KEY. A later transaction carrying an earlier row lowers
the minimum; if that value were key material the derived row's identity would change under
it and every confirmed cell already written against the old identity would be orphaned. So
the key stays the lot and the aggregate is a VALUE on that row.

⚠️ THE POPULATION IS THE KEY'S COMMITTED SOURCE ROWS, NOT THE BATCH. Measured 2026-09-10:
`_aggregate_affected_keys` lets the batch choose WHICH keys to recompute and then reads the
source table itself, so a late-arriving earlier row lowers the min. `count` already had
this property; min/max inherit it rather than reimplementing it.
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import anyio                                                          # noqa: E402
import pytest                                                         # noqa: E402

import enrichment.config                                              # noqa: E402
from database import crud, models, schemas                            # noqa: E402

TABLES = {
    "s129_bond_src": {
        "business_key": "bond_id",
        "column_types": {"bond_id": "string", "lot": "string",
                         "bonding_time": "string", "wafer_id": "string"},
    },
    "s129_bond_derived": {
        "business_key": "lot",
        "composite_key_source": ["lot"],
        "column_types": {"lot": "string", "bonding_time_min": "string",
                         "bonding_time_max": "string", "bond_count": "number",
                         "wafer_id": "string"},
    },
}

RULE = {
    "s129_lot_group": {
        "source_table": "s129_bond_src",
        "derived_table": "s129_bond_derived",
        "decision_key": ["lot"],
        "target_fields": ["wafer_id"],
        "aggregations": {
            "bonding_time_min": {"fn": "min", "column": "bonding_time"},
            "bonding_time_max": {"fn": "max", "column": "bonding_time"},
            "bond_count": "count",
        },
        "reference_views": [{
            "label": "bonds at the group's first time",
            "query": ("SELECT bond_id FROM s129_bond_src WHERE lot = :lot "
                      "AND bonding_time = :bonding_time_min ORDER BY bond_id"),
            "limit": 5,
        }],
    }
}


@pytest.fixture()
def env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    path = tmp_path / "enrichment_rules.json"
    path.write_text(json.dumps(RULE), encoding="utf-8")
    monkeypatch.setattr(enrichment.config, "ENRICHMENT_RULES_PATH", str(path))
    return db_session


def _seed(db, rows, tx_id):
    batch = schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=dict(r), source_name="pipeline_parser",
                                           updated_by="watcher") for r in rows],
        transaction_id=tx_id, silent=True)
    crud.apply_batch_updates(db, "s129_bond_src", batch)


def _run_chain(db, tx_id):
    from chain.ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrichment.config.load_enrichment_chain_rules(known_tables=crud.TABLE_CONFIG)
    events = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == "s129_bond_src",
        DatabaseOutbox.processed_chain == False,          # noqa: E712
    ).order_by(DatabaseOutbox.id.asc()).all()
    evs = [e for e in events if (e.payload or {}).get("transaction_id") == tx_id]
    assert evs, f"no pending outbox events for {tx_id}"

    async def run():
        ok, err, _msgs = await process_chain_transaction_group(tx_id, evs, db, rules)
        assert ok, f"chain group failed: {err}"
        for e in evs:
            e.processed_chain = True
        db.commit()

    anyio.run(run)


def _derived(db):
    model = models.DYNAMIC_TABLES["s129_bond_derived"]
    return db.query(model).all()


def test_a_late_transaction_with_an_earlier_row_lowers_the_minimum(env):
    """🔴 THE GATE. t2 lands first, t1 (< t2) arrives in a SECOND transaction, and the
    derived row's minimum has to come down - which is only true if the aggregate is read
    from the key's committed rows rather than from the batch that woke it."""
    _seed(env, [{"bond_id": "B2", "lot": "LOT-A", "bonding_time": "2026-09-10T12:00:00"}],
          "tx-late-1")
    _run_chain(env, "tx-late-1")

    rows = _derived(env)
    assert len(rows) == 1
    assert rows[0].bonding_time_min == "2026-09-10T12:00:00"
    assert rows[0].bond_count == 1

    _seed(env, [{"bond_id": "B1", "lot": "LOT-A", "bonding_time": "2026-09-10T09:00:00"}],
          "tx-late-2")
    _run_chain(env, "tx-late-2")

    rows = _derived(env)
    assert len(rows) == 1, "the key is the lot, so the row's identity must not have moved"
    assert rows[0].bonding_time_min == "2026-09-10T09:00:00", "the later batch lowered it"
    assert rows[0].bonding_time_max == "2026-09-10T12:00:00", "and the max did not move"
    assert rows[0].bond_count == 2, "count still counts the key's rows, not the batch's"


def test_the_reference_view_may_bind_the_aggregate_and_runs_with_its_value(env):
    """③ - the view asks with the group's own number, which is the whole point of putting
    it on the row."""
    _seed(env, [
        {"bond_id": "B1", "lot": "LOT-B", "bonding_time": "2026-09-10T09:00:00"},
        {"bond_id": "B2", "lot": "LOT-B", "bonding_time": "2026-09-10T12:00:00"},
    ], "tx-view")
    _run_chain(env, "tx-view")

    rules = enrichment.config.load_enrichment_chain_rules(known_tables=crud.TABLE_CONFIG)
    # ⚰️ BOTH HALVES CARRY IT UNDER `params` NOW. The dedup half used to embed the
    # declaration under a key of its own (`enrichment`), which was a second copy of
    # `params` written by the same function; it retired when that half became a
    # registered mapper. Either half answers this. Filtered rather than indexed.
    rule = [r["params"] for r in rules
            if r.get("params", {}).get("name") == "s129_lot_group"][0]
    view = rule["reference_views"][0]

    assert "bonding_time_min" in view["required_binds"], view["required_binds"]

    row = _derived(env)[0]
    binds = enrichment.config.view_bind_values(
        rule, {"lot": row.lot, "bonding_time_min": row.bonding_time_min})

    assert enrichment.config.missing_binds(view, binds) == []
    _columns, rows = enrichment.config.execute_reference_view(env, view, binds)

    assert [r[0] for r in rows] == ["B1"], "only the bond at the group's first time"


def test_a_rule_whose_table_is_not_catalogued_falls_back_to_key_and_aggregates():
    """⚰️ THIS ASSERTED THE WHOLE CONTRACT UNTIL S-136 WIDENED IT to every column of the
    derived row. What it measures now is the FALLBACK: with no `derived_table` the catalogue
    cannot be read, and 「모른다」 must not narrow to 「없다」 - refusing every view of a rule
    whose table the caller cannot see would be worse than the behaviour that worked before.
    So it falls back to exactly what the rule alone can vouch for."""
    rule = {"decision_key": ["lot"], "aggregations": {"bonding_time_min": {"fn": "min"}}}

    assert enrichment.config.view_bind_names(rule) == {"lot", "bonding_time_min"}
    assert enrichment.config.view_bind_values(
        rule, {"lot": "L", "bonding_time_min": "t", "wafer_id": "W"}) == {
            "lot": "L", "bonding_time_min": "t"}


def test_a_value_the_derived_row_does_not_carry_is_absent_rather_than_none():
    """⚠️ `missing_binds` is the named refusal for 「this view cannot be asked」; filling a
    gap with None would turn that refusal into an empty result table."""
    rule = {"decision_key": ["lot"], "aggregations": {"bonding_time_min": {"fn": "min"}}}

    assert enrichment.config.view_bind_values(rule, {"lot": "L"}) == {"lot": "L"}


# ── ④ 검증: 고칠 자리를 이름으로 가리킨다 ──────────────────────────────────

def _refusal(aggregations):
    raw = {"source_table": "s129_bond_src", "derived_table": "s129_bond_derived",
           "decision_key": ["lot"], "target_fields": ["wafer_id"],
           "aggregations": aggregations}
    rule, why = enrichment.config._validate_rule("r", raw, TABLES)
    assert rule is None, f"expected a refusal, got {rule}"
    return why


def test_an_unsupported_function_is_refused_by_name():
    why = _refusal({"bonding_time_min": {"fn": "median", "column": "bonding_time"}})

    assert "bonding_time_min" in why and "median" in why, why
    assert "min" in why and "max" in why, "the refusal lists what IS supported"


def test_min_without_a_column_is_refused_because_it_has_nothing_to_read():
    why = _refusal({"bonding_time_min": {"fn": "min"}})

    assert "bonding_time_min" in why and "column" in why, why


def test_count_with_a_column_is_refused_rather_than_quietly_ignored():
    """⛔ `{"fn": "count", "column": "x"}` reads as 「do not count rows where x is blank」
    and this version does not count that way. Ignoring the key would make the declaration
    and the behaviour disagree in silence."""
    why = _refusal({"bond_count": {"fn": "count", "column": "bonding_time"}})

    assert "bond_count" in why and "count" in why, why


def test_an_aggregate_reading_a_column_the_source_does_not_have_is_refused_at_load():
    """🔴 OTHERWISE THE RULE STANDS AND THROWS LATER. Without this the typo surfaces as a
    failed ingestion rather than as a declaration error, which points at the wrong file."""
    why = _refusal({"bonding_time_min": {"fn": "min", "column": "no_such_column"}})

    assert "no_such_column" in why and "s129_bond_src" in why, why


def test_the_old_string_form_still_loads_unchanged():
    """⚠️ THE HALF THAT MUST NOT MOVE. Every rule on disk spells it `{"col": "count"}`."""
    raw = {"source_table": "s129_bond_src", "derived_table": "s129_bond_derived",
           "decision_key": ["lot"], "target_fields": ["wafer_id"],
           "aggregations": {"bond_count": "count"}}

    rule, why = enrichment.config._validate_rule("r", raw, TABLES)

    assert rule is not None, why
    assert rule["aggregations"] == {"bond_count": {"fn": "count", "column": None}}
