"""Cell value resolution: the tie, the tiebreak, and the repair of what the tie broke.

THE DEFECT THESE TESTS EXIST FOR
    `crud.compute_priority_value` ranked sources by the priority map alone. Every
    file-derived source name is unregistered, so every one of them returns 99 and
    THEY ALL TIE; `sorted` is stable, so the winner fell to dict insertion order,
    and the write path loads the stored layers first and appends the incoming one
    last - so the INCUMBENT won every tie. A later delivery carrying a corrected
    value was stored in `cell_sources` and then discarded in silence, because the
    resolved value did not move and `has_changed` gates the column write, the audit
    log and the outbox event together.

HOW EACH PROPERTY IS PROVED
    Not by asserting the new behaviour and calling it a day. The old resolution is
    INJECTED back (`_legacy_compute_priority_value`) and the same scenario is shown
    to produce the stale value - so a green run here cannot also be green against
    the broken code. The injected resolver is a byte-for-byte copy of what the file
    contained before this change, including its `sorted` call.

    The two direction tests are deliberately named so that ALPHABETICAL order and
    RECENCY disagree: `aaa_old`/`zzz_new` and `zzz_old`/`aaa_new`. A resolver that
    fell back to `source_name` without ever reading `ingested_at` would pass one and
    fail the other, so passing both is what pins the axis.

[Isolation] `cvres_test_` prefix (server-pm memory: the bonding_log trap).
"""
from datetime import datetime

import pytest

import chain_replay
from database import crud, models, schemas

RES_TABLES = {
    "cvres_test_map": {
        "business_key": "part_no",
        "column_types": {"part_no": "string", "pitch": "string", "note": "string"},
    },
}

OLD_TS = datetime(2026, 1, 1, 0, 0, 0)
NEW_TS = datetime(2026, 6, 1, 0, 0, 0)


@pytest.fixture()
def res_env(db_session):
    models.init_dynamic_models(RES_TABLES)
    crud.TABLE_CONFIG.update(RES_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    yield db_session


# ---------------------------------------------------------------------------
# The resolution as it stood BEFORE this change. Kept verbatim so the injection
# tests below are a real mutation and not a paraphrase of one.
# ---------------------------------------------------------------------------

def _legacy_compute_priority_value(sources, manual_priority_source=None, table_name=None,
                                   ingested_at_by_source=None):
    if not sources:
        return None, None
    if manual_priority_source and manual_priority_source in sources:
        val_data = sources[manual_priority_source]
        val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
        return val, manual_priority_source
    priority_map = crud.resolve_priority_map(table_name)
    sorted_sources = sorted(sources.keys(), key=lambda k: priority_map.get(k, 99))
    top_source = sorted_sources[0]
    val_data = sources[top_source]
    val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
    return val, top_source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed(db, rows, source_name, tx_id="seed", updated_by="test"):
    items = [schemas.GeneralUpdateItem(business_key_val=r["part_no"], updates=dict(r),
                                       source_name=source_name, updated_by=updated_by)
             for r in rows]
    crud.apply_batch_updates(db, "cvres_test_map", schemas.GeneralUpdateBatch(
        updates=items, transaction_id=tx_id, silent=True))


def _row(db, part_no):
    m = models.DYNAMIC_TABLES["cvres_test_map"]
    return db.query(m).filter(m.business_key_val == part_no).first()


def _backdate(db, source_name, when):
    """Pin a stored layer's `ingested_at` so the test's axis is the timestamp and
    not the clock resolution of two writes microseconds apart."""
    db.query(models.CellSource).filter(
        models.CellSource.table_name == "cvres_test_map",
        models.CellSource.source_name == source_name,
    ).update({"ingested_at": when}, synchronize_session=False)
    db.commit()


def _layers(db, row_id, col):
    return {s.source_name: s.value for s in db.query(models.CellSource).filter(
        models.CellSource.table_name == "cvres_test_map",
        models.CellSource.row_id == row_id,
        models.CellSource.column_name == col).all()}


def _audit(db, row_id, col):
    return db.query(models.AuditLog).filter(
        models.AuditLog.table_name == "cvres_test_map",
        models.AuditLog.row_id == row_id,
        models.AuditLog.column_name == col).all()


def _deliver_twice(db, older_source, newer_source):
    """The production shape: one file delivers a value, a later file corrects it.

    Both source names are unregistered, so they TIE on the priority map - which is
    the whole population of file-derived sources.
    """
    _seed(db, [{"part_no": "P1", "pitch": "1"}], source_name=older_source, tx_id="d1")
    _backdate(db, older_source, OLD_TS)
    _seed(db, [{"part_no": "P1", "pitch": "7"}], source_name=newer_source, tx_id="d2")
    _backdate(db, newer_source, NEW_TS)
    return _row(db, "P1")


# ---------------------------------------------------------------------------
# A. the resolver
# ---------------------------------------------------------------------------

def _entry(value, ts):
    return {"value": value, "timestamp": ts.isoformat(), "updated_by": "test"}


def test_among_tied_sources_the_newest_delivery_wins():
    sources = {"aaa_old.csv": _entry("1", OLD_TS), "zzz_new.csv": _entry("7", NEW_TS)}
    assert crud.compute_priority_value(sources) == ("7", "zzz_new.csv")


def test_the_winner_is_recency_not_alphabetical_order():
    """The mirror of the test above. A resolver that only ever fell through to
    `source_name` would pass one of these two and fail this one."""
    sources = {"zzz_old.csv": _entry("1", OLD_TS), "aaa_new.csv": _entry("7", NEW_TS)}
    assert crud.compute_priority_value(sources) == ("7", "aaa_new.csv")


def test_the_answer_does_not_depend_on_the_order_the_caller_built_the_dict_in():
    a = {"aaa_old.csv": _entry("1", OLD_TS), "zzz_new.csv": _entry("7", NEW_TS)}
    b = {"zzz_new.csv": _entry("7", NEW_TS), "aaa_old.csv": _entry("1", OLD_TS)}
    assert crud.compute_priority_value(a) == crud.compute_priority_value(b)
    # ... and the old resolution is exactly what did depend on it.
    assert (_legacy_compute_priority_value(a)
            != _legacy_compute_priority_value(b)), \
        "the injected legacy resolver must be observed disagreeing with itself, or " \
        "this test is not measuring the defect"


def test_equal_timestamps_fall_to_source_name_and_stay_stable():
    a = {"b.csv": _entry("B", NEW_TS), "a.csv": _entry("A", NEW_TS)}
    b = {"a.csv": _entry("A", NEW_TS), "b.csv": _entry("B", NEW_TS)}
    assert crud.compute_priority_value(a) == ("A", "a.csv")
    assert crud.compute_priority_value(b) == ("A", "a.csv")


def test_a_dated_layer_outranks_an_undated_one():
    sources = {"legacy.csv": {"value": "1"}, "dated.csv": _entry("7", OLD_TS)}
    assert crud.compute_priority_value(sources) == ("7", "dated.csv")


def test_a_timestamp_may_arrive_out_of_band_for_a_payload_that_cannot_carry_one():
    """`main.fetch_and_merge_metadata` builds `{source: value}` because that dict IS
    the client-facing cell contract. It supplies the timestamps separately."""
    flat = {"aaa_old.csv": "1", "zzz_new.csv": "7"}
    assert crud.compute_priority_value(flat) == ("1", "aaa_old.csv"), \
        "with no timestamps at all the total order is the source name"
    assert crud.compute_priority_value(
        flat, ingested_at_by_source={"aaa_old.csv": OLD_TS, "zzz_new.csv": NEW_TS}
    ) == ("7", "zzz_new.csv")


# --- invariants that must NOT move -----------------------------------------

def test_user_still_outranks_a_newer_machine_layer():
    sources = {"user": _entry("HUMAN", OLD_TS), "zzz_new.csv": _entry("7", NEW_TS)}
    assert crud.compute_priority_value(sources) == ("HUMAN", "user")


def test_a_registered_source_still_outranks_a_newer_unregistered_one():
    sources = {"chain_ingestion": _entry("CHAIN", OLD_TS),
               "zzz_new.csv": _entry("7", NEW_TS)}
    assert crud.compute_priority_value(sources) == ("CHAIN", "chain_ingestion")


def test_a_manual_pin_still_wins_outright():
    sources = {"aaa_old.csv": _entry("1", OLD_TS), "zzz_new.csv": _entry("7", NEW_TS)}
    assert crud.compute_priority_value(sources, "aaa_old.csv") == ("1", "aaa_old.csv")


def test_recency_only_breaks_a_tie_it_never_promotes_across_ranks():
    """Level 2 must be unable to outrank level 1. `custom_script` (3) is older than
    an unregistered file (99) and still wins."""
    sources = {"custom_script": _entry("SCRIPT", OLD_TS),
               "aaa_new.csv": _entry("7", NEW_TS)}
    assert crud.compute_priority_value(sources) == ("SCRIPT", "custom_script")


# ---------------------------------------------------------------------------
# B. the write path - the actual defect, end to end
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("older,newer", [("aaa_old.csv", "zzz_new.csv"),
                                         ("zzz_old.csv", "aaa_new.csv")])
def test_a_corrected_redelivery_is_displayed_and_not_discarded(res_env, older, newer):
    row = _deliver_twice(res_env, older, newer)
    res_env.refresh(row)
    assert _layers(res_env, row.row_id, "pitch") == {older: "1", newer: "7"}, \
        "both layers must be stored - this is a resolution defect, not a storage one"
    assert row.pitch == "7", "the later delivery's corrected value must be what is displayed"


@pytest.mark.parametrize("older,newer", [("aaa_old.csv", "zzz_new.csv"),
                                         ("zzz_old.csv", "aaa_new.csv")])
def test_injecting_the_old_resolution_brings_the_stale_value_back(res_env, monkeypatch,
                                                                 older, newer):
    """THE MUTATION CHECK. Put the pre-change resolver back and the same scenario
    stores the correction and displays the stale value - which is precisely the
    production symptom. If this test ever goes green with the new resolver in
    place, the test above proves nothing."""
    monkeypatch.setattr(crud, "compute_priority_value", _legacy_compute_priority_value)
    row = _deliver_twice(res_env, older, newer)
    res_env.refresh(row)
    assert _layers(res_env, row.row_id, "pitch") == {older: "1", newer: "7"}
    assert row.pitch == "1", \
        "the injected defect must be observed discarding the correction"


def test_the_corrected_redelivery_is_no_longer_silent(res_env):
    """The value moved, so `has_changed` is true, so the write path emits history.
    Under the defect it emitted nothing at all - no column write, no audit row, no
    outbox event - which is why the loss was invisible."""
    row = _deliver_twice(res_env, "aaa_old.csv", "zzz_new.csv")
    logs = _audit(res_env, row.row_id, "ROW_UPDATE")
    assert any("pitch" in (lg.new_value or "") and "7" in (lg.new_value or "")
               for lg in logs), \
        "the correction must leave a history entry, not change the display in silence"


def _undate(db, source_name):
    """Blank a stored layer's `ingested_at`, the way a row predating the column would."""
    db.query(models.CellSource).filter(
        models.CellSource.table_name == "cvres_test_map",
        models.CellSource.source_name == source_name,
    ).update({"ingested_at": None}, synchronize_session=False)
    db.commit()


def test_an_undated_layer_does_not_outrank_a_dated_delivery_on_the_write_path(res_env):
    """The write path used to substitute `datetime.now()` for a NULL `ingested_at`
    when assembling the resolver's input. That was decoration while nothing read the
    timestamp; the moment recency became the tiebreak it inverted the rule, because
    the substitute is generated AFTER the incoming layer was stamped and is therefore
    always the largest timestamp present. An undated legacy layer would have beaten
    every dated delivery forever.

    The resolver's own `test_a_dated_layer_outranks_an_undated_one` cannot catch this:
    it hands the resolver a None, and the defect was that this caller never passed one.
    """
    _seed(res_env, [{"part_no": "P1", "pitch": "1"}], source_name="aaa_old.csv", tx_id="d1")
    _undate(res_env, "aaa_old.csv")
    _seed(res_env, [{"part_no": "P1", "pitch": "7"}], source_name="zzz_new.csv", tx_id="d2")
    row = _row(res_env, "P1")
    res_env.refresh(row)
    assert _layers(res_env, row.row_id, "pitch") == {"aaa_old.csv": "1", "zzz_new.csv": "7"}
    assert row.pitch == "7", "an undated layer must not be treated as the newest one"


def test_a_human_value_survives_a_newer_file_delivery(res_env):
    """The layering invariant, through the real write path rather than by assertion."""
    _seed(res_env, [{"part_no": "P1", "pitch": "HUMAN"}], source_name="user", tx_id="h")
    _backdate(res_env, "user", OLD_TS)
    _seed(res_env, [{"part_no": "P1", "pitch": "7"}], source_name="zzz_new.csv", tx_id="f")
    row = _row(res_env, "P1")
    res_env.refresh(row)
    assert row.pitch == "HUMAN"


# ---------------------------------------------------------------------------
# C. R3 - the repair of cells that are ALREADY wrong
# ---------------------------------------------------------------------------

def _make_stale_cell(db, monkeypatch, older="aaa_old.csv", newer="zzz_new.csv"):
    """Damage the data the way production damaged it: with the defect itself.

    A hand-built stale row would only prove the repair works on a shape the test
    author imagined. Running the real write path under the injected legacy resolver
    produces the real shape.
    """
    monkeypatch.setattr(crud, "compute_priority_value", _legacy_compute_priority_value)
    row = _deliver_twice(db, older, newer)
    monkeypatch.undo()
    db.refresh(row)
    assert row.pitch == "1", "the fixture must actually be stale before it is repaired"
    return row


def test_recompute_dry_run_enumerates_the_stale_cell_and_writes_nothing(res_env, monkeypatch):
    row = _make_stale_cell(res_env, monkeypatch)
    stats = chain_replay.recompute_display_values(res_env, "cvres_test_map",
                                                  log=lambda *_: None)
    assert stats["mode"] == "dry-run"
    assert stats["cells_changed"] == 1
    assert stats["changed_by_tiebreak"] == 1
    change = stats["changes"][0]
    assert (change["row_id"], change["column"]) == (row.row_id, "pitch")
    assert (change["old_value"], change["new_value"]) == ("1", "7")
    assert change["winning_source"] == "zzz_new.csv"
    assert change["sources"] == ["aaa_old.csv", "zzz_new.csv"]
    res_env.refresh(row)
    assert row.pitch == "1", "a dry-run must change nothing"
    assert _audit(res_env, row.row_id, "pitch") == []


def test_recompute_apply_repairs_the_cell(res_env, monkeypatch):
    row = _make_stale_cell(res_env, monkeypatch)
    stats = chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                                  log=lambda *_: None)
    assert stats["cells_changed"] == 1
    res_env.refresh(row)
    assert row.pitch == "7"
    assert _layers(res_env, row.row_id, "pitch") == {"aaa_old.csv": "1", "zzz_new.csv": "7"}, \
        "R3 must not create, delete or modify a single stored layer"


def test_recompute_writes_history_for_every_value_it_changes(res_env, monkeypatch):
    """The product owner's condition: a value that changes with no history entry is
    the same defect wearing different clothes."""
    row = _make_stale_cell(res_env, monkeypatch)
    chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                          log=lambda *_: None)
    logs = _audit(res_env, row.row_id, "pitch")
    assert len(logs) == 1
    lg = logs[0]
    assert (lg.old_value, lg.new_value) == ("1", "7")
    assert lg.source_name == chain_replay.R3_AUDIT_SOURCE
    assert lg.updated_by == "resolved:zzz_new.csv"


def test_recompute_is_idempotent(res_env, monkeypatch):
    _make_stale_cell(res_env, monkeypatch)
    chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                          log=lambda *_: None)
    second = chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                                   log=lambda *_: None)
    assert second["cells_changed"] == 0


def test_recompute_never_touches_a_cell_with_one_layer(res_env):
    """THE SAFETY GATE, proved rather than asserted: a single-layer cell has no tie,
    and a ZERO-layer cell would resolve to a blank. Both are excluded by the same
    `len(srcs) < 2` guard, so a full-table run cannot blank a column it does not own."""
    _seed(res_env, [{"part_no": "P1", "pitch": "1", "note": "keep"}],
          source_name="only.csv", tx_id="s")
    row = _row(res_env, "P1")
    # An out-of-band write that no layer knows about: the pass must leave it alone.
    row.note = "TOUCHED_ELSEWHERE"
    res_env.commit()
    stats = chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                                  log=lambda *_: None)
    assert stats["cells_examined"] == 0
    assert stats["cells_changed"] == 0
    res_env.refresh(row)
    assert row.note == "TOUCHED_ELSEWHERE"


def test_recompute_leaves_a_human_value_alone(res_env):
    _seed(res_env, [{"part_no": "P1", "pitch": "HUMAN"}], source_name="user", tx_id="h")
    _backdate(res_env, "user", OLD_TS)
    _seed(res_env, [{"part_no": "P1", "pitch": "7"}], source_name="zzz_new.csv", tx_id="f")
    stats = chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                                  log=lambda *_: None)
    # Two multi-layer cells: both writers set `part_no` and `pitch`. The pass looked
    # at both and changed neither, which is the point - `user` wins on both.
    assert stats["cells_examined"] == 2
    assert stats["cells_changed"] == 0
    row = _row(res_env, "P1")
    res_env.refresh(row)
    assert row.pitch == "HUMAN"


def test_recompute_honours_a_human_pin(res_env, monkeypatch):
    """A pin says "show me this one". The recompute reads it through
    `compute_priority_value`'s existing short-circuit, so a pinned cell resolves to
    the pinned layer and does not move."""
    row = _make_stale_cell(res_env, monkeypatch)
    crud.set_cell_manual_priority_batch(
        res_env, "cvres_test_map",
        [{"row_id": row.row_id, "column_name": "pitch"}], "aaa_old.csv")
    res_env.refresh(row)
    assert row.pitch == "1"
    stats = chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                                  log=lambda *_: None)
    assert stats["cells_changed"] == 0
    res_env.refresh(row)
    assert row.pitch == "1"


def test_recompute_repairs_drift_toward_the_pinned_layer_not_the_newest(res_env, monkeypatch):
    """A pin decides WHICH LAYER wins; it does not freeze the materialised column.

    So a pinned cell whose display has drifted away from the layer the human chose is
    repaired back TO THE PIN - not to the newest layer, which is what would happen if
    the recompute ignored pins. The counter for this is `pinned_changed`; it was
    previously named `pinned_unchanged` while being incremented on exactly the cells
    that did change, so nothing was measuring this.
    """
    row = _make_stale_cell(res_env, monkeypatch)
    crud.set_cell_manual_priority_batch(
        res_env, "cvres_test_map",
        [{"row_id": row.row_id, "column_name": "pitch"}], "aaa_old.csv")
    # Drift the display away from both layers, out of band.
    res_env.query(models.DYNAMIC_TABLES["cvres_test_map"]).filter_by(
        row_id=row.row_id).update({"pitch": "999"}, synchronize_session=False)
    res_env.commit()

    stats = chain_replay.recompute_display_values(res_env, "cvres_test_map", apply=True,
                                                  log=lambda *_: None)
    assert stats["pinned_examined"] == 1
    assert stats["cells_changed"] == 1
    assert stats["pinned_changed"] == 1
    res_env.refresh(row)
    assert row.pitch == "1", "repaired to the PINNED layer, not to the newest one"


def test_recompute_column_scope_is_respected(res_env, monkeypatch):
    row = _make_stale_cell(res_env, monkeypatch)
    stats = chain_replay.recompute_display_values(res_env, "cvres_test_map",
                                                  columns=["note"], apply=True,
                                                  log=lambda *_: None)
    assert stats["cells_changed"] == 0
    res_env.refresh(row)
    assert row.pitch == "1"


def test_recompute_refuses_an_undeclared_column(res_env):
    with pytest.raises(chain_replay.ReplayRefused):
        chain_replay.recompute_display_values(res_env, "cvres_test_map",
                                              columns=["no_such_col"],
                                              log=lambda *_: None)
