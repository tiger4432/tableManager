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
    - one blank-decision-key row -> must be skipped and counted.
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
        {"equipment": "", "event_time": "T9", "chip_id": "C9"},  # blank key
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
    assert stats["rows_scanned"] == 8          # 2 chained + 5 unchained + 1 blank
    assert stats["skipped_blank"] == 1
    assert stats["distinct_combinations"] == 3  # EQP0_T0, EQP1_T1, EQP2_T2
    assert stats["already_derived"] == 1        # EQP0_T0
    assert stats["new_combinations"] == 2       # EQP1_T1, EQP2_T2
    assert stats["created_rows"] == 0
    assert sorted(stats["sample_new_keys"]) == ["EQP1_T1", "EQP2_T2"]

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
    assert stats["created_rows"] == 2
    assert stats["new_combinations"] == 2
    assert stats["already_derived"] == 1
    assert stats["skipped_blank"] == 1

    rows = {r.business_key_val: r for r in _derived_rows(db)}
    assert set(rows) == {"EQP0_T0", "EQP1_T1", "EQP2_T2"}
    # The backfill must never create blank-decision-key combinations.
    for r in rows.values():
        assert r.equipment and str(r.equipment).strip() != ""
        assert r.event_time and str(r.event_time).strip() != ""

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
# 3. idempotency + limit
# ---------------------------------------------------------------------------

def test_apply_rerun_is_idempotent(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)
    first = bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    assert first["created_rows"] == 2

    second = bf.run_backfill(db, _rule(), apply=True, log=lambda *_: None)
    assert second["new_combinations"] == 0
    assert second["created_rows"] == 0
    assert second["already_derived"] == 3
    assert len(_derived_rows(db)) == 3


def test_limit_caps_new_identities_per_run(bkfl_env):
    db = bkfl_env
    _seed_standard_fixture(db)

    first = bf.run_backfill(db, _rule(), apply=True, limit=1, log=lambda *_: None)
    assert first["created_rows"] == 1
    assert first["limit_skipped"] == 1
    assert len(_derived_rows(db)) == 2  # 1 pre-existing + 1 backfilled

    second = bf.run_backfill(db, _rule(), apply=True, limit=1, log=lambda *_: None)
    assert second["created_rows"] == 1
    assert second["limit_skipped"] == 0
    assert len(_derived_rows(db)) == 3

    third = bf.run_backfill(db, _rule(), apply=True, limit=1, log=lambda *_: None)
    assert third["created_rows"] == 0


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
