# -*- coding: utf-8 -*-
"""운영에서는 아무것도 적지 않습니다 -- 표에서 행이 사라지면 원장에서 그 행의 사실이 걷힙니다.

S-54-b, ruling 132. A scope cannot reach a deleted row: `source_raw_ref` is built from a
row's `order_by` values at the preparation boundary, so once the row is gone there is
nothing to build it from and its atoms stay however wide the scope is spelled. That is a
structural cannot, not a width -- which is why DELETE waited for its own instrument instead
of riding the EDIT path and quietly doing nothing.

🔴 THE INSTRUMENT IS A NOTE TAKEN WHILE THE ROW WAS STILL THERE. `ledger_source_row_ref`
records `(relation, row_id) -> (source_who, source_raw_ref)` in the SAME transaction as the
atoms, so "the atom exists and its index row does not" is unreachable rather than repairable.
The delete then asks by RELATION, which is what the outbox knows -- teaching the outbox the
ledger's sources is the layer violation the ruling refused.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill, followup, runtime_v2, schema             # noqa: E402


@pytest.fixture(autouse=True)
def no_views(monkeypatch):
    """🔴 VIEWS ARE NOT THIS FILE'S SUBJECT, AND THE SEAM IS ONE NAME (판정 158).

    Since S-65-d a deletion also withdraws for the sources reading views on the deleted
    row's table, and it asks in exactly one place. Blocking that name keeps these cases
    about the base table's own index, which is what they were written to score.
    """
    monkeypatch.setattr(followup, "view_followers_of",
                        lambda engine, setup, table: ([], []))
from ledger.roleframe import SOURCE_ROW_REF_COLUMN                    # noqa: E402
from ledger.source_preparation import FRAME_ROW_ID_COLUMN             # noqa: E402

RELATION = "dt_log"
OCCURRED_AT = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)


# ------------------------------------------------------- the note the translation takes

def frame(pairs):
    return pd.DataFrame([{FRAME_ROW_ID_COLUMN: row_id, SOURCE_ROW_REF_COLUMN: ref}
                         for row_id, ref in pairs])


def result_with(claim_refs):
    """A stand-in for one molecule's compile result.

    ⚠️ IT HOLDS `ledger_rows`, WHICH IS WHAT THE RUNTIME READS. It used to hold a
    DataFrame, and when the compiler stopped building one per molecule (S-64) this double
    was the only thing still claiming it did -- the double has to imitate the real result,
    not the one it replaced.
    """
    from ledger.ledger_frame import LedgerRows

    return SimpleNamespace(ledger_rows=LedgerRows(
        tuple({"source_raw_ref": ref} for ref in claim_refs), {}))


def claim_ref(*row_refs):
    """The atom's ref, spelled the way `_claim_source_raw_ref` spells it -- built rather
    than typed, so a test cannot pass on a shape the builder never produces."""
    return json.dumps({"event": "dt_log:e", "rows": sorted(set(row_refs))},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def index(frames, claim_refs):
    return runtime_v2._row_ref_index(
        SimpleNamespace(relation=RELATION), frames, [result_with(claim_refs)])


def test_the_index_stores_the_ref_the_LEDGER_holds_not_the_rows_own():
    """🔴 THE TWO REFS ARE DIFFERENT STRINGS, AND THE WITHDRAWAL MATCHES THE SECOND. A row's
    ref is `<relation>:<json of its order_by values>`; the ATOM carries that string only
    when the molecule is one row, and `{"event":…,"rows":[…]}` otherwise. An index holding
    the row's spelling would find no atom to withdraw and report success having removed
    nothing -- which is the failure this whole feature exists to prevent, wearing the
    feature's own clothes."""
    one, two = 'dt_log:{"a":1}', 'dt_log:{"a":2}'
    claim = claim_ref(one, two)
    assert index([frame([("R1", one), ("R2", two)])], [claim]) == (
        (RELATION, "R1", claim), (RELATION, "R2", claim))


def test_a_single_row_molecule_is_the_collapsed_spelling_and_is_still_found():
    """⚠️ THE CASE A READER OF ONLY THE JSON SHAPE WOULD SILENTLY MISS, and it is most
    molecules: when the rows ARE the event the builder collapses to the bare ref."""
    one = 'dt_log:{"a":1}'
    assert index([frame([("R1", one)])], [one]) == ((RELATION, "R1", one),)


def test_one_row_under_two_claims_keeps_both():
    """One event may emit several sentences over different subsets of its rows, so a row
    belongs to more than one claim ref -- and each has to be withdrawable."""
    one = 'dt_log:{"a":1}'
    other = claim_ref(one)
    pairs = index([frame([("R1", one)])], [one, other])
    assert sorted(pairs) == sorted([(RELATION, "R1", other), (RELATION, "R1", one)])


def test_an_empty_ref_names_no_row_at_all():
    """⚠️ AND IT IS NOT THE SAME AS AN UNREADABLE ONE. An unreadable ref comes back as
    itself, because it is still the exact string the ledger stores and a caller matching on
    it still matches. An EMPTY one names nothing, and returning `("",)` for it would put a
    line in the index whose ref matches every atom that has none."""
    from ledger.roleframe import claim_source_row_refs

    assert claim_source_row_refs("") == ()
    assert claim_source_row_refs(None) == ()
    assert claim_source_row_refs("not json at all") == ("not json at all",)
    assert claim_source_row_refs('{"event":"e"}') == ('{"event":"e"}',)


def test_a_frame_without_the_columns_contributes_nothing_rather_than_raising():
    """A frame this shallow is a test double, and the write it feeds is the write it always
    was -- an index that refused to be built would take the translation down with it."""
    assert index([pd.DataFrame([{"other": 1}])], ['dt_log:{"a":1}']) == ()
    assert index([], ['dt_log:{"a":1}']) == ()


def test_the_write_door_carries_it(monkeypatch):
    """🔴 EVERY WRITE MUST BUILD THE INDEX, because a delete reads it to find what to
    withdraw and an index only some writes filled would name a handful of rows out of
    millions -- a delete would then look like it worked.

    ⚰️ THERE WERE TWO DOORS. `execute_cursor_batch` was the forward scan and this asserted
    the same line in both; it retired with S-113 ⓐ (ruling 221) because after S-76 the live
    path drains through events and no product code called it. One door is now the whole of
    "every write", which is why this reads as a single assertion rather than a weaker one.
    """
    import inspect

    body = inspect.getsource(runtime_v2.execute_scoped_batch)
    assert "row_refs=preview.row_refs" in body


# ------------------------------------------------------------ and what the delete then does

class FakeStore:
    def __init__(self, index):
        self.index = list(index)
        self.withdrawn = []
        self.forgotten = []

    def row_refs_for(self, relation, row_ids):
        wanted = {str(item) for item in row_ids}
        return [(who, ref) for rel, row_id, who, ref in self.index
                if rel == relation and row_id in wanted]

    def withdraw(self, source, refs):
        self.withdrawn.append((source, tuple(refs)))
        return len(refs)

    def forget_row_refs(self, relation, row_ids):
        self.forgotten.append((relation, tuple(str(item) for item in row_ids)))
        return len(row_ids)


INDEX = [(RELATION, "R1", "dt_job", "dt_log:one"),
         (RELATION, "R1", "other_source", "dt_log:one"),
         (RELATION, "R2", "dt_job", "dt_log:two"),
         ("somewhere_else", "R1", "dt_job", "somewhere_else:one")]


@pytest.fixture
def store(monkeypatch):
    made = FakeStore(INDEX)
    monkeypatch.setattr("ledger.store.LedgerStore", lambda engine: made)
    return made


def test_one_deleted_row_withdraws_every_source_that_read_that_table(store):
    """🔴 THE INDEX IS KEYED BY RELATION BECAUSE THAT IS WHAT THE OUTBOX KNOWS. Two sources
    may read one table; the row's disappearance is one fact about both of them, and neither
    the outbox nor this step has to be told which sources exist."""
    result = backfill.withdraw_deleted_rows(None, None, RELATION, ["R1"], apply=True)
    assert sorted(store.withdrawn) == [("dt_job", ("dt_log:one",)),
                                       ("other_source", ("dt_log:one",))]
    assert result["sources"]["dt_job"]["withdrawn"] == 1
    assert result["applied"] is True


def test_the_index_rows_go_last(store):
    """⚠️ ORDER IS THE REPAIRABILITY. While the index rows are here the withdrawal can be
    run again; dropping them first would make a run that died in the middle unrepeatable,
    and the atoms would stay with nothing left pointing at them."""
    backfill.withdraw_deleted_rows(None, None, RELATION, ["R1", "R2"], apply=True)
    assert store.withdrawn, "nothing was withdrawn at all"
    assert store.forgotten == [(RELATION, ("R1", "R2"))]


def test_a_dry_run_writes_nothing_and_still_says_what_it_would_do(store):
    result = backfill.withdraw_deleted_rows(None, None, RELATION, ["R1"])
    assert store.withdrawn == [] and store.forgotten == []
    assert result["applied"] is False
    assert result["sources"]["dt_job"] == {"refs": 1, "withdrawn": 0}


def test_a_row_the_ledger_never_translated_costs_nothing(store):
    """㉧ AT THE DELETE END. Most rows in this database belong to tables no source reads,
    and the index simply has no line for them -- so there is no withdrawal to run and no
    index row to drop."""
    result = backfill.withdraw_deleted_rows(None, None, RELATION, ["R-UNKNOWN"], apply=True)
    assert store.withdrawn == [] and store.forgotten == []
    assert result["sources"] == {} and result["applied"] is False


def test_the_same_delete_twice_changes_nothing_the_second_time(store):
    """㉡′. The first pass drops the index rows, so the second finds no refs, withdraws
    nothing and forgets nothing -- idempotent by construction rather than by a guard."""
    backfill.withdraw_deleted_rows(None, None, RELATION, ["R1"], apply=True)
    store.index = [row for row in store.index if row[1] != "R1" or row[0] != RELATION]
    store.withdrawn.clear()
    store.forgotten.clear()
    again = backfill.withdraw_deleted_rows(None, None, RELATION, ["R1"], apply=True)
    assert store.withdrawn == [] and store.forgotten == [] and again["applied"] is False


def test_a_source_with_no_row_index_is_named_rather_than_passed_over(store):
    """🔴 판정 136. A source reading a VIEW has no `row_id` to index by, so this step can do
    nothing for it -- and a quiet zero is indistinguishable from "there was nothing to
    withdraw". The absence is structurally correct (nothing writes an outbox DELETE for a
    view), which is the reason to say it plainly rather than treat it as a gap."""
    setup = SimpleNamespace(snapshot=SimpleNamespace(source_plans={
        "on_a_view": SimpleNamespace(relation=RELATION, frame_row_id=None),
        "on_a_table": SimpleNamespace(relation=RELATION, frame_row_id="row_id"),
        "elsewhere": SimpleNamespace(relation="other", frame_row_id=None),
    }))
    result = backfill.withdraw_deleted_rows(None, setup, RELATION, ["R1"], apply=True)
    assert result["no_row_index"] == ["on_a_view"], (
        "only the sources that read THIS relation and cannot be served")


# ------------------------------------------------------------- and the queue routes it there

def test_a_delete_is_withdrawn_from_the_index_not_rescoped(monkeypatch):
    """⛔ NOT A WIDER SCOPE. `rescope` is replaced with a detonator: a delete that reached it
    would aim at the CURRENT translation of rows that no longer exist, find no refs, and
    report success having withdrawn nothing."""
    def boom(*args, **kwargs):
        raise AssertionError("a delete was sent through the scope path")

    seen = {}

    monkeypatch.setattr(backfill, "rescope", boom)
    monkeypatch.setattr(backfill, "withdraw_deleted_rows",
                        lambda engine, setup, relation, row_ids, apply=False: seen.update(
                            relation=relation, rows=list(row_ids), apply=apply)
                        or {"sources": {"dt_job": {"withdrawn": 2}}, "forgotten": 2})
    followup.reset()
    followup.enqueue(RELATION, ["R1", "R2"], "DELETE")
    done = followup.drain_once(None, None)
    followup.reset()
    assert seen == {"relation": RELATION, "rows": ["R1", "R2"], "apply": True}
    assert done["event_type"] == "DELETE" and done["forgotten"] == 2


def test_a_failed_delete_is_named_and_not_requeued(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr(backfill, "withdraw_deleted_rows", boom)
    followup.reset()
    followup.enqueue(RELATION, ["R1"], "DELETE")
    done = followup.drain_once(None, None)
    assert "RuntimeError" in done["error"] and followup.queue_depth() == 0
    followup.reset()


# ----------------------------------------------------- and what the table means, in Postgres

@pytest.fixture
def real_store(pg_engine):
    from ledger.store import LedgerStore

    connection = pg_engine.raw_connection()
    try:
        schema.ensure_schema(connection)
    finally:
        connection.close()
    return LedgerStore(pg_engine)


def test_the_index_survives_a_re_translation_by_moving(real_store):
    """A rescope writes the pair again, and the ref may have MOVED -- a corrected
    `order_by` value is exactly what a rescope exists for -- so the newest translation wins
    rather than colliding."""
    connection = real_store.connection()
    try:
        real_store._write_row_refs(connection, "dt_job", [(RELATION, "R1", "dt_log:old")])
        real_store._write_row_refs(connection, "dt_job", [(RELATION, "R1", "dt_log:new")])
        connection.commit()
    finally:
        connection.close()
    assert real_store.row_refs_for(RELATION, ["R1"]) == [("dt_job", "dt_log:new")]


def test_two_sources_reading_one_table_each_keep_their_own_line(real_store):
    connection = real_store.connection()
    try:
        real_store._write_row_refs(connection, "dt_job", [(RELATION, "R9", "a")])
        real_store._write_row_refs(connection, "other", [(RELATION, "R9", "b")])
        connection.commit()
    finally:
        connection.close()
    assert sorted(real_store.row_refs_for(RELATION, ["R9"])) == [
        ("dt_job", "a"), ("other", "b")]
    assert real_store.forget_row_refs(RELATION, ["R9"]) == 2
    assert real_store.row_refs_for(RELATION, ["R9"]) == []
