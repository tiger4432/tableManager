"""Retroactive enrichment backfill verification (server/enrichment_backfill.py).

The operator CLI over this module is `server/scripts/backfill_enrichment.py`
(unchanged path and flags); the admin count/run routes reach the same functions
through `retroactive.py`. This file tests the module, so both callers are covered
at the one place the semantics live.

⚠️ This file used to `sys.path.insert(0, SCRIPTS_DIR)` and import the CLI directly.
That insertion is why a broken route shipped under a green suite: pytest shares one
interpreter, so after this module was collected `import backfill_enrichment`
succeeded for every later test - including any test written to prove that the
runtime could not import it. Do not reintroduce it. The import environment is
proved in a child process by `test_prod_import_env.py`.

Covers:
- dry-run counts on a seeded fixture (scanned / distinct / already / new / blank)
  and that a dry-run writes nothing (derived rows + outbox untouched)
- --apply creates exactly the new combinations through the REAL mapper + REAL
  write path; pre-existing derived rows stay byte-untouched (fixture activates
  the defect axis: the pre-existing key has extra unchained source rows, so a
  buggy "touch existing" would change its chip_count)
- provenance: created cells carry source_name="enrichment_backfill" which can
  never outrank user edits (priority 99 vs 0)
- derived-table outbox events from the backfill do not re-trigger the same
  enrichment rule (trigger is the SOURCE table)
- refusals: disabled rule (unless --force-disabled), loader-rejected rule with
  the loader's reason, unknown rule name
- idempotency: re-run after apply reports 0 new
- --limit caps new identities per run; a follow-up run picks up the rest

[Isolation] Table names use the bkfl_test_* prefix so they can never collide
with the user's real table_config (see server-pm memory: bonding_log case).
"""
import json
import uuid

import anyio
import pytest

import enrichment_backfill as bf
import enrichment_config
from database import crud, models, schemas

BKFL_TABLES = {
    "bkfl_test_src": {
        "business_key": "log_key",
        "composite_key_source": ["equipment", "event_time", "chip_id"],
        "composite_key_separator": "_",
        "column_types": {
            "log_key": "string",
            "equipment": "string",
            "event_time": "string",
            "chip_id": "string",
            "lot_hint": "string",
        },
    },
    "bkfl_test_derived": {
        "business_key": "job_id",
        "composite_key_source": ["equipment", "event_time"],
        "composite_key_separator": "_",
        "column_types": {
            "job_id": "string",
            "equipment": "string",
            "event_time": "string",
            "wafer_id": "string",
            "chip_count": "number",
            "lot_hint": "string",
        },
    },
    # --- the two OTHER legal key contracts, because they are where a partial key
    # can silently destroy data and the table above cannot show it.
    # `_validate_rule` accepts `composite_key_source ⊆ decision_key` OR
    # `business_key ∈ decision_key`; `bkfl_test_derived` is the first with an
    # EQUAL subset, which is the one shape where every identity spelling agrees.
    #
    # (a) business_key IS a decision-key column. If a partial key were spelled by
    #     the declaration, the blank column would BE the identity: every partial
    #     key on this table resolves to the empty string, they all collapse onto
    #     one row, and `apply_batch_updates` overwrites across them.
    "bkfl_test_bkkey": {
        "business_key": "equipment",
        "column_types": {"equipment": "string", "event_time": "string",
                         "wafer_id": "string"},
    },
    # (b) composite_key_source is a PROPER subset of the decision key. A partial
    #     key whose blank column sits OUTSIDE comp_src would spell the identity of
    #     a COMPLETE key and land on that row.
    "bkfl_test_subkey": {
        "business_key": "job_id",
        "composite_key_source": ["event_time"],
        "composite_key_separator": "_",
        "column_types": {"job_id": "string", "equipment": "string",
                         "event_time": "string", "wafer_id": "string"},
    },
}

RULES_FILE = {
    "bkfl_rule": {
        "source_table": "bkfl_test_src",
        "derived_table": "bkfl_test_derived",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
        "list_columns": ["chip_count", "lot_hint"],
        "aggregations": {"chip_count": "count"},
    },
    "bkfl_disabled": {
        "source_table": "bkfl_test_src",
        "derived_table": "bkfl_test_derived",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
        "enabled": False,
    },
    "bkfl_broken": {
        # missing derived_table -> loader must reject with its reason
        "source_table": "bkfl_test_src",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
    },
    "bkfl_bkkey_rule": {
        "source_table": "bkfl_test_src",
        "derived_table": "bkfl_test_bkkey",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
    },
    "bkfl_subkey_rule": {
        "source_table": "bkfl_test_src",
        "derived_table": "bkfl_test_subkey",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
    },
}


@pytest.fixture()
def bkfl_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(BKFL_TABLES)
    crud.TABLE_CONFIG.update(BKFL_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps(RULES_FILE), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    return db_session


def _seed_source(db, rows, tx_id=None, silent=True):
    """Ingest rows into the source table WITHOUT running the chain worker -
    this is exactly the 'rows predate the rule' condition the backfill fixes."""
    tx_id = tx_id or f"tx_{uuid.uuid4().hex[:8]}"
    updates = [
        schemas.GeneralUpdateItem(updates=dict(row), source_name="pipeline_parser",
                                  updated_by="watcher")
        for row in rows
    ]
    crud.apply_batch_updates(
        db, "bkfl_test_src",
        schemas.GeneralUpdateBatch(updates=updates, transaction_id=tx_id, silent=silent),
    )
    return tx_id


def _run_chain_for_tx(db, tx_id):
    """Process one transaction's outbox events through the REAL chain path -
    used to create the 'already derived' baseline."""
    from chain_ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrichment_config.load_enrichment_chain_rules(known_tables=crud.TABLE_CONFIG)
    assert rules, "enrichment chain rules must be synthesized"

    events = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == "bkfl_test_src",
        DatabaseOutbox.processed_chain == False,  # noqa: E712
    ).order_by(DatabaseOutbox.id.asc()).all()
    evs = [e for e in events if (e.payload or {}).get("transaction_id") == tx_id]
    assert evs, f"no pending outbox events for tx {tx_id}"

    async def run():
        ok, err, _msgs = await process_chain_transaction_group(tx_id, evs, db, rules)
        assert ok, f"chain group failed: {err}"
        for e in evs:
            e.processed_chain = True
        db.commit()

    anyio.run(run)


def _derived_rows(db):
    model = models.DYNAMIC_TABLES["bkfl_test_derived"]
    return db.query(model).order_by(model.business_key_val.asc()).all()


def _rule(force_disabled=False, name="bkfl_rule"):
    return bf.load_rule(name, crud.TABLE_CONFIG, force_disabled=force_disabled)


def _outbox_count(db):
    return db.query(models.DatabaseOutbox).count()


def _seed_standard_fixture(db):
    """Baseline used by several tests.

    - EQP0_T0: chained (already derived, chip_count=2) PLUS one extra unchained
      source row -> if the backfill wrongly touched existing rows, chip_count
      would flip to 3. This activates the defect axis on purpose.
    - EQP1_T1 (3 rows) and EQP2_T2 (1 row): unchained -> the backfill targets.
    - one PARTIAL decision key (equipment blank, event_time present) -> since the
      2026-08-05 ruling this is WORKED, not dropped: it is a real identity built
      on what survived. It used to land in the skip bucket.
    - one WHOLLY blank decision key -> the only remaining refusal, because it
      points at nothing. Present so `skipped_no_key` is exercised rather than
      asserted at 0 forever.
    """
    tx0 = _seed_source(db, [
        {"equipment": "EQP0", "event_time": "T0", "chip_id": "C1", "lot_hint": "LOT_0"},
        {"equipment": "EQP0", "event_time": "T0", "chip_id": "C2", "lot_hint": "LOT_0"},
    ])
    _run_chain_for_tx(db, tx0)

    _seed_source(db, [
        {"equipment": "EQP0", "event_time": "T0", "chip_id": "C3"},  # extra, unchained
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C4", "lot_hint": "LOT_A"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C5", "lot_hint": "LOT_A"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C6"},
        {"equipment": "EQP2", "event_time": "T2", "chip_id": "C7", "lot_hint": "LOT_B"},
        {"equipment": "", "event_time": "T9", "chip_id": "C9"},   # PARTIAL key -> "_T9"
        {"equipment": "", "event_time": "", "chip_id": "C0"},     # no key at all
    ])


# ---------------------------------------------------------------------------
# 1. dry-run
# ---------------------------------------------------------------------------

def test_dry_run_counts_and_writes_nothing(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)

    derived_before = [(r.row_id, r.business_key_val, r.chip_count, r.updated_at)
                      for r in _derived_rows(db)]
    outbox_before = _outbox_count(db)

    stats = bf.run_backfill(db, _rule(), apply=False, log=lambda *_: None)

    assert stats["mode"] == "dry-run"
    assert stats["rows_scanned"] == 9          # 2 chained + 5 unchained + 1 partial + 1 keyless
    # THE BUCKET, AFTER THE RULING. Only the keyless row is skipped; the partial
    # one is an identity. Before 2026-08-05 this pair read `skipped_blank == 2`
    # and `distinct_combinations == 3`, and an operator comparing releases would
    # see the skip count fall with no explanation - hence the rename.
    assert stats["skipped_no_key"] == 1
    assert stats["distinct_combinations"] == 4  # EQP0_T0, EQP1_T1, EQP2_T2, _T9
    assert stats["partial_key_combinations"] == 1
    assert stats["already_derived"] == 1        # EQP0_T0
    assert stats["new_combinations"] == 3       # EQP1_T1, EQP2_T2, _T9
    assert stats["created_rows"] == 0
    assert sorted(stats["sample_new_keys"]) == ["EQP1_T1", "EQP2_T2", "_T9"]
    assert "skipped_blank" not in stats, (
        "the old name is back with new arithmetic behind it - that is the exact "
        "shape of a dry-run number that lies across releases")

    # A dry-run writes nothing: derived rows and outbox are untouched.
    derived_after = [(r.row_id, r.business_key_val, r.chip_count, r.updated_at)
                     for r in _derived_rows(db)]
    assert derived_after == derived_before
    assert _outbox_count(db) == outbox_before


# ---------------------------------------------------------------------------
# 2. apply
# ---------------------------------------------------------------------------

def test_apply_creates_exactly_new_combinations(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)

    pre = {r.business_key_val: r for r in _derived_rows(db)}
    assert set(pre) == {"EQP0_T0"}
    pre_row = pre["EQP0_T0"]
    pre_snapshot = {c.name: getattr(pre_row, c.name) for c in pre_row.__table__.columns}
    pre_sources = sorted(
        (s.column_name, s.source_name, str(s.value))
        for s in db.query(models.CellSource).filter(
            models.CellSource.table_name == "bkfl_test_derived",
            models.CellSource.row_id == pre_row.row_id,
        ).all()
    )

    stats = bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    assert stats["created_rows"] == 3
    assert stats["new_combinations"] == 3
    assert stats["already_derived"] == 1
    assert stats["skipped_no_key"] == 1

    rows = {r.business_key_val: r for r in _derived_rows(db)}
    assert set(rows) == {"EQP0_T0", "EQP1_T1", "EQP2_T2", "_T9"}
    # The backfill must never create an identity with NOTHING in its key: the
    # keyless source row produced no row, and no row carries an empty identity
    # (an empty `business_key_val` would collapse every future keyless write onto
    # one row and let `apply_batch_updates` overwrite across it).
    for bk, r in rows.items():
        assert crud.clean_str_value(bk) != ""
        assert not (crud.is_blank_value(r.equipment) and crud.is_blank_value(r.event_time))

    # The partial-key identity keeps what survived and says nothing about what
    # did not - it is not "equipment = the empty string is a real machine".
    partial = rows["_T9"]
    assert crud.is_blank_value(partial.equipment)
    assert partial.event_time == "T9"
    assert partial.wafer_id is None, "backfill must never write target_fields"

    # New rows: keys + display hints + idempotent counts, targets stay blank.
    r1 = rows["EQP1_T1"]
    assert r1.job_id == "EQP1_T1"
    assert r1.equipment == "EQP1" and r1.event_time == "T1"
    assert r1.chip_count == 3
    assert r1.lot_hint == "LOT_A"
    assert r1.wafer_id is None, "backfill must never write target_fields"
    r2 = rows["EQP2_T2"]
    assert r2.chip_count == 1 and r2.lot_hint == "LOT_B" and r2.wafer_id is None

    # Pre-existing derived row: byte-untouched, even though its combination has
    # an extra unchained source row (chip_count must NOT become 3).
    post_row = rows["EQP0_T0"]
    post_snapshot = {c.name: getattr(post_row, c.name) for c in post_row.__table__.columns}
    assert post_snapshot == pre_snapshot
    assert post_snapshot["chip_count"] == 2
    post_sources = sorted(
        (s.column_name, s.source_name, str(s.value))
        for s in db.query(models.CellSource).filter(
            models.CellSource.table_name == "bkfl_test_derived",
            models.CellSource.row_id == post_row.row_id,
        ).all()
    )
    assert post_sources == pre_sources


def test_apply_provenance_and_priority(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)
    bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)

    rows = {r.business_key_val: r for r in _derived_rows(db)}
    new_row = rows["EQP1_T1"]

    # Every cell layer written by the backfill is tagged enrichment_backfill.
    srcs = db.query(models.CellSource).filter(
        models.CellSource.table_name == "bkfl_test_derived",
        models.CellSource.row_id == new_row.row_id,
    ).all()
    assert srcs, "backfilled cells must be recorded in the layering system"
    assert {s.source_name for s in srcs} == {bf.SOURCE_NAME}
    assert {s.updated_by for s in srcs} == {bf.SOURCE_NAME}

    # Layering: the backfill can never outrank user edits, and later chain
    # writes supersede it for the display value.
    assert crud.get_source_priority(bf.SOURCE_NAME) == 99
    assert crud.get_source_priority("user") == 0
    assert crud.get_source_priority("chain_ingestion") == 4

    # A user fills the target and a later increment arrives: user value stays.
    crud.apply_batch_updates(db, "bkfl_test_derived", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=new_row.row_id, updates={"wafer_id": "W123"},
                                  source_name="user", updated_by="tester")
    ], silent=True))
    tx = _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C99", "lot_hint": "LOT_A2"},
    ])
    _run_chain_for_tx(db, tx)
    refreshed = {r.business_key_val: r for r in _derived_rows(db)}["EQP1_T1"]
    assert refreshed.wafer_id == "W123"
    assert refreshed.chip_count == 4  # chain recount supersedes the backfill count
    assert refreshed.lot_hint == "LOT_A2"


def test_apply_outbox_events_do_not_retrigger_rule(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)
    outbox_before = _outbox_count(db)
    from sqlalchemy import func
    max_id_before = db.query(func.max(models.DatabaseOutbox.id)).scalar() or 0
    bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)

    # The writes emit outbox events through the normal hook (graph/chain
    # workers see them), tagged with the backfill's provenance...
    new_events = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.id > max_id_before,
        models.DatabaseOutbox.table_name == "bkfl_test_derived",
    ).all()
    assert _outbox_count(db) > outbox_before
    assert new_events
    assert all((e.payload or {}).get("source_name") == bf.SOURCE_NAME for e in new_events)

    # ...but running the REAL chain path over them is a no-op for this rule:
    # its trigger table is the SOURCE table, and these events are on the
    # derived table -> no re-trigger, no cycle.
    from chain_ingestion_worker import process_chain_transaction_group
    rules = enrichment_config.load_enrichment_chain_rules(known_tables=crud.TABLE_CONFIG)
    derived_before = [(r.row_id, r.chip_count) for r in _derived_rows(db)]

    async def run():
        ok, err, _ = await process_chain_transaction_group("bf_tx", new_events, db, rules)
        assert ok, err

    anyio.run(run)
    assert [(r.row_id, r.chip_count) for r in _derived_rows(db)] == derived_before


# ---------------------------------------------------------------------------
# 2-bis. THE SWEEP AND THE LIVE PATH MUST ANSWER A PARTIAL KEY IDENTICALLY
#
# The sweep WRITES, across the whole table, unattended. The live path can afford
# to be permissive because anything it leaves unresolved stays on a worklist for
# a person; a sweep that resolved the same case differently would overwrite in
# silence. So these tests never assert the backfill's answer on its own - they
# assert that it is the SAME answer, in both directions.
#
# The shape is deliberately the ambiguous one: a partial key matches MORE
# broadly, so `_<T>` and `EQPX_<T>` share their surviving key column and only the
# missing one tells them apart.
# ---------------------------------------------------------------------------

def _ambiguous_partial_shape(tag):
    """One complete identity and one partial identity that share `event_time`."""
    return [
        {"equipment": "EQPX", "event_time": tag, "chip_id": f"{tag}_A", "lot_hint": "L"},
        {"equipment": "", "event_time": tag, "chip_id": f"{tag}_B", "lot_hint": "L"},
        {"equipment": "", "event_time": tag, "chip_id": f"{tag}_C", "lot_hint": "L"},
    ]


def _shape_snapshot(db, tag):
    """The derived state for one key space, with the tag normalised out.

    Everything a divergence could show up in: the identity spelling, which key
    columns survived, the aggregate over the source rows the identity claims, and
    the target (which neither path may fill)."""
    return sorted(
        (r.business_key_val.replace(tag, "<T>"),
         crud.clean_str_value(r.equipment), crud.clean_str_value(r.event_time).replace(tag, "<T>"),
         float(r.chip_count), r.wafer_id)
        for r in _derived_rows(db) if crud.clean_str_value(r.event_time) == tag
    )


def test_sweep_and_live_chain_produce_the_same_answer_on_an_ambiguous_partial_key(bkfl_env):
    db = bkfl_env

    # The live path, on its own key space: the real chain worker over real outbox
    # events, which is what an ordinary increment does.
    tx = _seed_source(db, _ambiguous_partial_shape("TL"))
    _run_chain_for_tx(db, tx)
    live = _shape_snapshot(db, "TL")

    # The sweep, on an identical shape it never chained - the "these rows predate
    # the rule" condition the backfill exists for.
    _seed_source(db, _ambiguous_partial_shape("TB"))
    bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    swept = _shape_snapshot(db, "TB")

    assert swept == live, (
        "the retroactive sweep and the live increment disagree about a partial "
        f"decision key: sweep={swept} live={live}")
    # And the agreed answer is the one the ruling asks for - not "both refused".
    # Without this the equality above is satisfied by two empty sets.
    assert [row[0] for row in live] == ["EQPX_<T>", "_<T>"], (
        "the partial key produced no identity - both paths are still on the "
        "pre-2026-08-05 answer, and agreeing on it proves nothing")
    # The broader match must not reach into the complete key's rows.
    assert dict((row[0], row[3]) for row in live) == {"_<T>": 2.0, "EQPX_<T>": 1.0}


def test_the_sweep_recognises_the_live_paths_partial_identity_as_its_own(bkfl_env):
    """Direction 1: live wrote it, the sweep must find nothing left to do.

    If the two spelled a partial identity differently, the sweep would not see
    the live path's row and would INSERT a twin - two rows for one decision key,
    each holding half the evidence, and no error anywhere."""
    db = bkfl_env
    tx = _seed_source(db, _ambiguous_partial_shape("TS"))
    _run_chain_for_tx(db, tx)
    before = [(r.row_id, r.business_key_val, float(r.chip_count))
              for r in _derived_rows(db)]

    stats = bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)

    assert stats["already_derived"] == 2
    assert stats["new_combinations"] == 0 and stats["created_rows"] == 0
    assert [(r.row_id, r.business_key_val, float(r.chip_count))
            for r in _derived_rows(db)] == before


def test_the_live_path_recognises_the_sweeps_partial_identity_as_its_own(bkfl_env):
    """Direction 2, the one that matters for a table already swept.

    The sweep runs first, then the same source rows arrive at the chain worker
    (a re-ingestion, a replay). The live path must land ON the swept row."""
    db = bkfl_env
    tx = _seed_source(db, _ambiguous_partial_shape("TR"))
    bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    before = {r.business_key_val: r.row_id for r in _derived_rows(db)}
    assert set(before) == {"_TR", "EQPX_TR"}

    _run_chain_for_tx(db, tx)

    assert {r.business_key_val: r.row_id for r in _derived_rows(db)} == before, (
        "the live path forked a second identity off rows the sweep already "
        "claimed")


def test_one_predicate_gates_both_row_creation_and_candidate_resolution(bkfl_env,
                                                                        monkeypatch):
    """Structural, not behavioural: they agree because they call ONE function.

    Two paths that merely happen to hold the same answer today drift apart the
    day one of them is edited - which is exactly what had happened here, with
    `enrichment_candidates` on `all blank` while the mapper and this module were
    still on `any blank`. Moving the shared predicate must move BOTH gates; a
    surviving private copy shows up as one of these assertions not moving.
    """
    db = bkfl_env
    _seed_source(db, [{"equipment": "EQPQ", "event_time": "TQ", "chip_id": "CQ"}])
    rule = _rule()

    monkeypatch.setattr(enrichment_config, "key_is_wholly_blank",
                        lambda r, kv: True)

    stats = bf.run_backfill(db, rule, apply=True, log=lambda *_: None)
    assert stats["created_rows"] == 0 and _derived_rows(db) == [], (
        "row creation did not go through the shared predicate")

    import enrichment_candidates
    # A rule with a DECLARING view, so resolution gets past `not_declared` and
    # reaches the gate under test. The patched predicate short-circuits before
    # any view executes, so the query body is never read.
    probe_rule = dict(rule, reference_views=[
        {"label": "ref", "candidate_for": {"wafer_id": "lot_hint"},
         "query": "SELECT lot_hint FROM bkfl_test_src WHERE event_time = :event_time",
         "required_binds": ["event_time"]},
    ])
    verdict = enrichment_candidates.resolve_target_candidate(
        db, probe_rule, {"equipment": "EQPQ", "event_time": "TQ"}, "wafer_id")
    assert verdict["reason"] == enrichment_candidates.REASON_NO_DECISION_KEY, (
        "candidate resolution did not go through the shared predicate")


def _rows_of(db, table):
    model = models.DYNAMIC_TABLES[table]
    return db.query(model).order_by(model.business_key_val.asc()).all()


def test_a_partial_key_is_refused_when_the_blank_column_IS_the_business_key(bkfl_env):
    """`business_key ∈ decision_key`, no composite: the identity would be EMPTY.

    `crud._update_row_business_key` copies `updates[business_key]` verbatim, so a
    partial key whose blank column is the business key resolves to "" - and every
    such row on the table resolves to the same "", i.e. one row that successive
    writes overwrite. The mapper cannot out-vote that (crud composes the stored
    identity, the mapper only hints), so the row is REFUSED and counted under its
    own name instead of being written into a collision.
    """
    db = bkfl_env
    rule = _rule(name="bkfl_bkkey_rule")
    tx = _seed_source(db, [
        {"equipment": "", "event_time": "T8", "chip_id": "D1"},
        {"equipment": "", "event_time": "T9", "chip_id": "D2"},
        {"equipment": "EQPK", "event_time": "T8", "chip_id": "D7"},  # complete: unaffected
    ])

    stats = bf.run_backfill(db, rule, apply=True, log=lambda *_: None)
    assert stats["skipped_unexpressible_key"] == 2
    assert stats["skipped_no_key"] == 0, "these rows HAVE a key - do not fold the two facts"
    rows = [r.business_key_val for r in _rows_of(db, "bkfl_test_bkkey")]
    assert rows == ["EQPK"], (
        "a partial key was written onto a table that cannot address it")

    # The live path refuses identically - it is the same function.
    _run_chain_for_tx(db, tx)
    assert [r.business_key_val for r in _rows_of(db, "bkfl_test_bkkey")] == ["EQPK"]


def test_a_partial_key_is_refused_when_it_would_spell_a_complete_keys_identity(bkfl_env):
    """`composite_key_source ⊊ decision_key`: the blank column sits outside comp_src.

    The surviving columns ARE the whole composite source, so crud's recompute
    succeeds and hands the partial row the COMPLETE key's identity - then finds
    that row as a conflict and runs [Silent Merge & Overwrite], merging the
    partial row's values over it and deleting one row. Measured, not theorised.
    Refused by name; the complete key's row must be untouched.
    """
    db = bkfl_env
    rule = _rule(name="bkfl_subkey_rule")
    tx = _seed_source(db, [
        {"equipment": "EQPZ", "event_time": "T7", "chip_id": "D3"},
        {"equipment": "", "event_time": "T7", "chip_id": "D4"},
    ])

    stats = bf.run_backfill(db, rule, apply=True, log=lambda *_: None)
    assert stats["skipped_unexpressible_key"] == 1
    rows = {r.business_key_val: r for r in _rows_of(db, "bkfl_test_subkey")}
    assert set(rows) == {"T7"}
    assert rows["T7"].equipment == "EQPZ", (
        "the complete key's own column was overwritten by a partial-key row")

    row_ids = {bk: r.row_id for bk, r in rows.items()}
    _run_chain_for_tx(db, tx)
    after = {r.business_key_val: r for r in _rows_of(db, "bkfl_test_subkey")}
    assert {bk: r.row_id for bk, r in after.items()} == row_ids
    assert after["T7"].equipment == "EQPZ"


def test_a_partial_key_counts_both_storages_of_its_missing_column(bkfl_env):
    """NULL and '' are one decision key, and the count must say so.

    A blank key component cannot be asked with equality: binding `''` matches the
    empty-string rows and misses the NULL ones, and SQL's `NULL = NULL` is not
    true. Both storages occur in real data - `''` from a parsed-but-empty cell,
    NULL from a column the row never carried - so an equality-bound recount
    writes an undercount into the derived row and nothing reports it.
    """
    db = bkfl_env
    _seed_source(db, [
        {"equipment": "", "event_time": "T6", "chip_id": "D5"},
        {"event_time": "T6", "chip_id": "D6"},
    ])
    # `crud` normalises a blank write to NULL, so seeding alone produces ONE
    # storage and the fixture would not activate the axis it is named for (a
    # mutation that reads only the last SQL group survives it). The empty string
    # is put in directly - which is how it gets there in production too: rows
    # written before the normalisation, or by anything that is not this write
    # path.
    src = models.DYNAMIC_TABLES["bkfl_test_src"]
    victim = db.query(src).filter(src.chip_id == "D5").one()
    victim.equipment = ""
    db.commit()
    stored = sorted((r.equipment is None, r.equipment)
                    for r in db.query(src).filter(src.event_time == "T6").all())
    assert stored == [(False, ""), (True, None)], (
        f"fixture must hold BOTH storages of blank, got {stored}")

    bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)

    rows = {r.business_key_val: r for r in _derived_rows(db)}
    assert set(rows) == {"_T6"}, "the two storages of blank made two identities"
    assert float(rows["_T6"].chip_count) == 2.0, (
        "the recount saw only one storage of the missing key column")


def test_a_partial_identity_survives_a_later_refinement_write(bkfl_env):
    """The identity must not evaporate on the SECOND write to the same row.

    `crud`'s composite recompute reads the ROW's stored values, and a blank
    component makes it produce `None` - the fallback that rescues the insert
    (`is_new and update_item.business_key_val`) does not apply to an update. It is
    only safe because the composite source columns ARE the decision key and
    therefore never appear in `changed_cols` for an existing row. That is a
    property of the current code, not a promise it makes, so it is pinned here:
    if a later write ever re-derived, `business_key_val` would go NULL and the
    row would become unaddressable - visible in the grid, findable by nothing.
    """
    db = bkfl_env
    _seed_source(db, [{"equipment": "", "event_time": "T5", "chip_id": "E1",
                       "lot_hint": "L1"}])
    bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    row = _derived_rows(db)[0]
    assert row.business_key_val == "_T5"

    tx = _seed_source(db, [{"equipment": "", "event_time": "T5", "chip_id": "E2",
                            "lot_hint": "L2"}])
    _run_chain_for_tx(db, tx)

    rows = _derived_rows(db)
    assert len(rows) == 1
    assert rows[0].row_id == row.row_id
    assert rows[0].business_key_val == "_T5", "the identity was re-derived away"
    assert rows[0].job_id == "_T5"
    assert float(rows[0].chip_count) == 2.0
    assert rows[0].lot_hint == "L2"


def test_dry_run_and_apply_agree_on_which_rows_are_eligible(bkfl_env):
    """The operator approves the dry-run's number and gets the apply's rows.

    Dry-run is not merely apply-without-writes: it strips the count aggregations
    to skip the recount queries. That asymmetry must never reach ELIGIBILITY -
    if it did, the preview and the run would be counting different populations
    and nothing would say so.
    """
    db = bkfl_env
    _seed_standard_fixture(db)

    dry = bf.run_backfill(db, _rule(), apply=False, log=lambda *_: None)
    run = bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)

    assert run["created_rows"] == dry["new_combinations"]
    for k in ("rows_scanned", "skipped_no_key", "skipped_unexpressible_key",
              "distinct_combinations", "partial_key_combinations",
              "already_derived", "new_combinations"):
        assert run[k] == dry[k], f"dry-run and apply disagree on '{k}'"
    assert sorted(run["sample_new_keys"]) == sorted(dry["sample_new_keys"])


# ---------------------------------------------------------------------------
# 3. idempotency + limit
# ---------------------------------------------------------------------------

def test_apply_rerun_is_idempotent(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)
    first = bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    assert first["created_rows"] == 3

    second = bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    assert second["new_combinations"] == 0
    assert second["created_rows"] == 0
    assert second["already_derived"] == 4
    assert len(_derived_rows(db)) == 4
    # Idempotency has to cover the partial key too: if its identity were spelled
    # differently on the second pass, the re-run would create a twin instead of
    # recognising its own row.
    assert second["partial_key_combinations"] == 0


def test_limit_caps_new_identities_per_run(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)

    first = bf.run_backfill(db, _rule(), apply=True, limit=1, log=lambda *_: None)
    assert first["created_rows"] == 1
    assert first["limit_skipped"] == 2
    assert len(_derived_rows(db)) == 2  # 1 pre-existing + 1 backfilled

    second = bf.run_backfill(db, _rule(), apply=True, limit=1, log=lambda *_: None)
    assert second["created_rows"] == 1
    assert second["limit_skipped"] == 1
    assert len(_derived_rows(db)) == 3

    third = bf.run_backfill(db, _rule(), apply=True, limit=1, log=lambda *_: None)
    assert third["created_rows"] == 1
    assert third["limit_skipped"] == 0
    assert len(_derived_rows(db)) == 4

    fourth = bf.run_backfill(db, _rule(), apply=True, limit=1, log=lambda *_: None)
    assert fourth["created_rows"] == 0


def test_limit_must_be_positive(bkfl_env):
    db = bkfl_env
    with pytest.raises(bf.BackfillRefused, match="positive"):
        bf.run_backfill(db, _rule(), apply=True, limit=0, log=lambda *_: None)


# ---------------------------------------------------------------------------
# 4. refusals (every refusal states why)
# ---------------------------------------------------------------------------

def test_disabled_rule_refused_unless_forced(bkfl_env):
    with pytest.raises(bf.BackfillRefused, match="disabled"):
        _rule(name="bkfl_disabled")
    # explicit override validates the rule as if enabled
    rule = _rule(name="bkfl_disabled", force_disabled=True)
    assert rule["name"] == "bkfl_disabled"
    assert rule["derived_table"] == "bkfl_test_derived"


def test_loader_rejected_rule_fails_loudly_with_reason(bkfl_env):
    with pytest.raises(bf.BackfillRefused, match="'derived_table' is required"):
        _rule(name="bkfl_broken")


def test_unknown_rule_and_missing_file_refused(bkfl_env, tmp_path, monkeypatch):
    with pytest.raises(bf.BackfillRefused, match="available rules"):
        _rule(name="ghost_rule")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH",
                        str(tmp_path / "nope.json"))
    with pytest.raises(bf.BackfillRefused, match="not found"):
        _rule()


def test_uninitialized_table_refused(bkfl_env, monkeypatch):
    db = bkfl_env
    rule = _rule()
    monkeypatch.delitem(models.DYNAMIC_TABLES, "bkfl_test_src")
    with pytest.raises(bf.BackfillRefused, match="not initialized"):
        bf.run_backfill(db, rule, log=lambda *_: None)


# ---------------------------------------------------------------------------
# 9. the bounded read: scan_limit must bound the DERIVED read too
#
# `scan_limit` caps the source scan, and used to cap nothing else: every call
# still loaded every existing derived business key into a Python set first. On a
# request path that is unbounded work behind a bounded-looking knob. The full CLI
# run keeps the whole-table snapshot, because that is what "complete" means.
# ---------------------------------------------------------------------------

def _spy_iter_pages(monkeypatch):
    """Record which tables the shared keyset walk was pointed at.

    Watching `iter_pages` rather than a returned label on purpose: the label is
    what the code CLAIMS, the walk is the unbounded read itself.
    """
    import keyset_scan

    real = keyset_scan.iter_pages
    seen = []

    def spy(db, model, *a, **kw):
        seen.append(model.__table__.name)
        return real(db, model, *a, **kw)

    monkeypatch.setattr(keyset_scan, "iter_pages", spy)
    return seen


def test_sampled_run_never_walks_the_derived_table(bkfl_env, monkeypatch):
    db = bkfl_env
    _seed_standard_fixture(db)

    seen = _spy_iter_pages(monkeypatch)
    stats = bf.run_backfill(db, _rule(), apply=False, scan_limit=2,
                            log=lambda *_: None)

    assert stats["existing_lookup"] == "probe"
    assert "bkfl_test_src" in seen, "the source scan must still happen"
    assert "bkfl_test_derived" not in seen, (
        "a scan_limit-ed run walked the whole derived table - the preview is "
        "O(derived identities) no matter how small the sample is")
    assert stats["rows_scanned"] == 2


def test_full_run_still_snapshots_every_existing_identity(bkfl_env, monkeypatch):
    """The CLI's semantics are unchanged: a complete run diffs against everything."""
    db = bkfl_env
    _seed_standard_fixture(db)

    seen = _spy_iter_pages(monkeypatch)
    stats = bf.run_backfill(db, _rule(), apply=False, log=lambda *_: None)

    assert stats["existing_lookup"] == "preload"
    assert "bkfl_test_derived" in seen, (
        "a full backfill stopped reading the whole derived table - 'new' would "
        "then mean something narrower than 'not present anywhere'")


def test_probe_and_preload_agree_when_the_sample_covers_everything(bkfl_env):
    """The bounded read must be EXACT for its sample, not merely cheaper.

    Sized so the sample IS the whole table: then the two resolvers are answering
    the identical question and any disagreement is the probe being wrong. The
    fixture carries a genuinely pre-existing identity (EQP0_T0), so a probe that
    silently found nothing would show up as already_derived collapsing to 0.
    """
    db = bkfl_env
    _seed_standard_fixture(db)

    full = bf.run_backfill(db, _rule(), apply=False, log=lambda *_: None)
    sampled = bf.run_backfill(db, _rule(), apply=False, scan_limit=1000,
                              log=lambda *_: None)

    assert full.pop("existing_lookup") == "preload"
    assert sampled.pop("existing_lookup") == "probe"
    assert sampled == full
    assert full["already_derived"] == 1, "fixture must actually exercise the lookup"


def test_probe_keeps_an_identity_this_run_created_out_of_already_derived(bkfl_env):
    """A row created in chunk 1 must still be refinable in chunk 2.

    This is the whole reason the probe memoises. Apply mode commits per chunk, so
    the naive implementation - ask the database fresh, every chunk - reads back
    the row it just wrote, files it under `already_derived`, and drops the later
    chunk's refinement write. The preload never had this problem because its
    snapshot predates the run; the probe has to reproduce that on purpose.
    """
    db = bkfl_env
    _seed_source(db, [
        {"equipment": "EQP7", "event_time": "T7", "chip_id": "C1", "lot_hint": "L"},
        {"equipment": "EQP7", "event_time": "T7", "chip_id": "C2", "lot_hint": "L"},
    ])

    stats = bf.run_backfill(db, _rule(), apply=True, scan_limit=2, chunk_size=1,
                            log=lambda *_: None)

    assert stats["chunks"] == 2, "fixture must actually span two chunks"
    assert stats["existing_lookup"] == "probe"
    assert stats["already_derived"] == 0, (
        "the run's own creation was read back as pre-existing")
    assert stats["created_rows"] == 1
    assert stats["updated_rows"] == 1, (
        "the second chunk's refinement write was dropped")

    rows = _derived_rows(db)
    assert [r.business_key_val for r in rows] == ["EQP7_T7"]
    assert float(rows[0].chip_count) == 2.0, (
        "the count aggregation must see both source rows")


def test_probe_reports_a_pre_existing_identity_it_did_not_create(bkfl_env):
    """The other half: a row that predates the run IS already_derived."""
    db = bkfl_env
    tx0 = _seed_source(db, [
        {"equipment": "EQP8", "event_time": "T8", "chip_id": "C1", "lot_hint": "L"},
    ])
    _run_chain_for_tx(db, tx0)
    assert [r.business_key_val for r in _derived_rows(db)] == ["EQP8_T8"]

    stats = bf.run_backfill(db, _rule(), apply=False, scan_limit=10,
                            log=lambda *_: None)
    assert stats["existing_lookup"] == "probe"
    assert stats["already_derived"] == 1
    assert stats["new_combinations"] == 0
