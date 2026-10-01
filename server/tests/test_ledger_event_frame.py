"""The existing-cursor -> pandas EventFrame boundary (`ledger/event_frame.py`).

Was `test_ledger_source_preparation.py`. Setup_version 6 retired the preparer (총괄
e14416950): a computed column is one the chain wrote into the relation, so the joined
`target_id` these tests used to read back through a fake join reader is the relation's own
column now, and a blank one is a blank cell in the frame. The properties are unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ast
import os

import pandas as pd
import pytest

from ledger.backfill import prepare_v2_cursor_batch
from ledger.event_frame import base_select_columns
from ledger.roleframe import (
    DeclarativeRoleMapper,
    MapperContext,
    RoleMapperImplementationRegistry,
    dry_run_event_frame,
)
from test_ledger_setup_bundle import logical_bundle
from test_ledger_setup_registry import snapshot


def base_select_columns_of(snapshot, source_id):
    """`(snapshot, source_id)` -> the authority's answer, in ONE place.

    ⚰️ `backfill.v2_base_select_columns` was this, in production code, with no production
    caller. It is deleted (2026-09-09) and the convenience lives here, where the callers
    actually are -- once, so `test_ledger_setup_boundary` imports it rather than spelling
    the same two lines a second time.
    """
    return base_select_columns(snapshot.source_plans[source_id])


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def base_rows(count=1):
    return pd.DataFrame([{
        # 판정 135: the engine reads `row_id` on EVERY source, declared or not, so a frame
        # standing in for one has to carry it -- the boundary checks that every column
        # `base_select_columns` names survived, and this is now one of them.
        "row_id": f"RID-{index:04d}",
        "record_id": f"R-{index:04d}",
        "join_id": f"J-{index:04d}",
        "source_id": f"IN-{index:04d}",
        "target_id": f"OUT-J-{index:04d}",
        "event_at": NOW + timedelta(seconds=index),
        "event_key": f"E-{index:04d}",
    } for index in range(count)])


def mappers():
    registry = RoleMapperImplementationRegistry()
    registry.register("map-transition-role", 1, DeclarativeRoleMapper)
    return registry.seal()


# ⚰️ RETIRED with the preparer (setup_version 6, 총괄 e14416950) - each measured a preparer, a
# join reader or what they produced, and none has a subject left: a preparer output owning
# event identity (twice), 1001 keys in two reads, the SQLAlchemy join reader, zero or many
# right rows, a missing join key, a None preparer output, an output never overwriting a
# recorded value, a late right row, the dependency replay worklist, the multi-core dt
# inventory preparer, a custom preparer's free hook, direct and custom preparers sharing the
# compiler, and the sealed preparer registry.


def test_existing_cursor_selects_only_base_physical_columns():
    compiled = snapshot()

    columns = base_select_columns_of(compiled, "input_rows")

    # 🔴 [총괄 f3bc02f6e] every source reads `row_id` - a relation without one is a view,
    #   and a view source is refused at load. (판정 136's 「asks for none」 was that view case.)
    # setup_version 6: `target_id` is the relation's own (the write join puts it there)
    # and `join_id` is read by nothing any more.
    assert columns == ("event_at", "event_key", "record_id", "row_id", "source_id", "target_id")


def test_an_event_frame_feeds_the_stage4_compiler_path():
    compiled = snapshot()
    base = base_rows()

    events = prepare_v2_cursor_batch(compiled, "input_rows", base)

    assert len(events) == 1
    event = events[0]
    assert event["target_id"].tolist() == ["OUT-J-0000"]
    assert event["source_id"].tolist() == ["IN-0000"]
    # 🔴 THE STORED SPELLING STAYS (총괄 e14416950 ③): every atom's `source_raw_ref` already
    # carries an empty join list, and a ref that changed spelling would stop matching its own
    # atoms.
    assert event.attrs["source_raw_ref"].endswith('"verified_joins":[]}')

    result = dry_run_event_frame(
        MapperContext(compiled, compiled.source_plans["input_rows"]), event, mappers())
    assert len(result.role_frame) == 1
    assert result.ledger_frame.iloc[0]["predicate"] == "moves_to"
    assert result.ledger_frame.iloc[0]["object_payload"] == {
        "type": "OutputEntity",
        "keys": {"output_id": "OUT-J-0000"},
        "qualifiers": {"event_key": "E-0000"},
    }


def test_missing_entity_identity_refuses_ITS_MOLECULE_not_the_page():
    """🔴 INVERTED (S-41, rulings 110 · 116). This used to assert that one row with no
    entity identity killed the WHOLE PAGE - and that is the defect, not the contract: an
    operator with one blank cell got nothing translated and no name for why. The gate has
    held a name for this fact all along (`no_identity`); the preparation was dying in
    front of it.

    What still holds is what this test was really protecting: nothing is compiled, and
    the cursor does not move on the strength of a molecule that was not built. The
    refusal is now a VALUE, so the caller can do both - land the rest and say what it
    refused."""
    compiled = snapshot()
    base = base_rows()
    base.loc[0, "target_id"] = None
    cursor = "BEFORE"

    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    assert events == ()
    assert len(refusals) == 1
    assert refusals[0].reason == "no_identity"
    assert refusals[0].rows == 1
    assert [a["path"] for a in refusals[0].addresses] == [
        "event_frame.rows[0].target_id"]
    assert cursor == "BEFORE"


def test_one_blank_row_refuses_one_molecule_and_the_others_land():
    """The whole point of the change, and a one-row fixture cannot show it: with a single
    molecule, "refused the molecule" and "refused the page" produce the same answer."""
    compiled = snapshot()
    base = base_rows(3)
    base.loc[1, "target_id"] = None

    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    assert len(events) == 2
    assert [event["source_id"].tolist()[0] for event in events] == ["IN-0000", "IN-0002"]
    assert len(refusals) == 1
    assert refusals[0].reason == "no_identity"
    assert refusals[0].addresses[0]["path"] == "event_frame.rows[1].target_id"


def test_a_refusal_names_the_COLUMN_in_its_sentence_not_only_its_code():
    """⚠️ IT DOES NOT PROVE "names the molecule AND the row", and the first draft of this
    test claimed it did. On a row-unit source the molecule's handle IS `rows[N]` - the
    same string as the cell address - so no assertion here can tell the two apart. The
    multi-row test below is where that claim is earned; this one holds the smaller fact
    that the sentence carries the column, so a refusal is readable without decoding the
    address."""
    compiled = snapshot()
    base = base_rows(2)
    base.loc[1, "target_id"] = None

    refusals = []
    prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    refusal, = refusals
    assert "target_id" in refusal.detail, refusal.detail
    assert refusal.addresses[0]["path"] == "event_frame.rows[1].target_id"


def test_a_page_whose_every_molecule_is_refused_is_values_not_an_exception():
    """Not an error: a page fully read and fully refused. `rows_read > 0` with
    `molecules == 0` is a thing the caller has to be able to SAY."""
    compiled = snapshot()
    base = base_rows(2)
    base["target_id"] = None

    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    assert events == ()
    assert len(refusals) == 2
    assert {r.reason for r in refusals} == {"no_identity"}


def _time_is_not_the_order_column():
    """The shipped majority shape: 13 of 15 v2 sources order by something other than
    their time column. In the two that do not (`lot_event`, `lot_slot_move`) a blank time
    is a blank cursor cell too, and the molecule is refused as `no_raw_ref` - the cursor is
    asked first (총괄 4b5964ab2)."""
    raw = logical_bundle()
    raw["sources"]["input_rows"]["read"]["order_by"] = ["record_id"]
    return raw


def test_a_blank_time_refuses_its_molecule_by_the_time_name():
    """A different name, because the operator fixes a different cell. `no_identity` sends
    them to the key column; this one sends them to the clock."""
    compiled = snapshot(_time_is_not_the_order_column())
    base = base_rows(2)
    base.loc[1, "event_at"] = None

    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    assert len(events) == 1
    refusal, = refusals
    assert refusal.reason == "missing_occurred_at"
    assert refusal.addresses[0]["path"] == "event_frame.rows[1].event_at"


def test_a_blank_ORDER_column_refuses_its_WHOLE_molecule_by_no_raw_ref():
    """S-41 ② (the cursor part, 총괄 4b5964ab2): `order_by` is the cursor, and a row names
    itself by it - a blank there leaves the row nothing to be said from. It was a PAGE
    refusal, and the box's dt_log showed what that costs: one job with an empty
    `dt_cell_key` stopped every follow-up that read it. Now the molecule holding the row
    goes, WHOLE (ruling 116): two rows share `E-SHARED`, one is blank, the refusal counts
    TWO - a molecule built from the other row alone would be a smaller event (the box's
    72-row job said `has_netdie` 71)."""
    compiled = snapshot(_time_is_not_the_order_column())
    base = base_rows(3)
    base.loc[0, "event_key"] = "E-SHARED"
    base.loc[1, "event_key"] = "E-SHARED"
    base.loc[1, "record_id"] = None

    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    assert [event["source_id"].tolist() for event in events] == [["IN-0002"]]
    refusal, = refusals
    assert (refusal.reason, refusal.rows) == ("no_raw_ref", 2)
    assert "E-SHARED" in refusal.detail and "fill record_id" in refusal.detail, refusal.detail
    assert list(refusal.addresses) == [{
        "code": "source_preparation_incomplete",
        "path": "bundle.sources.input_rows.read.order_by.record_id"}]


def test_a_multi_row_molecule_is_refused_WHOLE_and_counts_all_its_rows():
    """🔴 THE FIXTURE THE RULING RESERVED. On a row-unit source "the molecule" and "the
    row" are the same set, so every assertion above passes under either reading. Here two
    rows share one `event_key` and only one of them is blank: the whole event goes, its
    row count is TWO, and the neighbouring molecule still lands.

    Whole, because the event's instant is read from every row of the group in one pass -
    a group with a hole does not become a smaller event, it becomes one that cannot be
    built (ruling 116)."""
    compiled = snapshot()
    base = base_rows(3)
    base.loc[0, "event_key"] = "E-SHARED"
    base.loc[1, "event_key"] = "E-SHARED"
    base.loc[1, "target_id"] = None

    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    assert len(events) == 1, "the untouched molecule must still land"
    assert events[0]["source_id"].tolist() == ["IN-0002"]
    refusal, = refusals
    assert refusal.reason == "no_identity"
    assert refusal.rows == 2, "the refused molecule is two rows, not the one blank row"
    # BOTH handles, and here they are different strings: the molecule is named by its
    # group key and the empty cell by its row. One without the other leaves the operator
    # searching for the half that was dropped.
    assert "E-SHARED" in refusal.detail, refusal.detail
    assert "target_id" in refusal.detail, refusal.detail
    assert refusal.addresses[0]["path"] == "event_frame.rows[1].target_id"


def test_building_a_refused_molecule_touches_no_process_counter():
    """🔴 THE PREVIEW'S WHOLE CLAIM. Preparation names and counts the refusal as a VALUE;
    only an executing caller charges it to the gate. If this module recorded, a test run
    would move the numbers an operator reads the real run from."""
    from ledger import gate

    # ⚰️ THE INSTRUMENT CHANGED, THE SUBJECT DID NOT. This read `gate.refusal_report()`,
    # an envelope that retired with the refusals route (S-114). The counters it folded are
    # still here and are the better probe: the envelope could have gone on comparing equal
    # while one of the five underneath moved, because it dropped `rows_refused` and
    # `atoms_lost` into per-source buckets and summed the rest.
    def counters():
        return (gate.refusals(), gate.samples(), gate.rows_refused(),
                gate.atoms_lost(), gate.incomplete_molecules())

    before = counters()
    compiled = snapshot()
    base = base_rows()
    base.loc[0, "target_id"] = None

    refusals = []
    prepare_v2_cursor_batch(compiled, "input_rows", base, refusals=refusals)

    assert len(refusals) == 1
    assert counters() == before


def test_runtime_module_has_no_cursor_store_gate_atom_or_transaction_capability():
    # 🔴 ANCHORED TO THIS FILE, NOT TO THE WORKING DIRECTORY. The path used to be
    # "server/ledger/source_preparation.py" (now `event_frame.py`), which resolves only when pytest is invoked
    # from the repository root; run from `server/` -- which is how the suite is run -- the
    # module is not there and the test fails on a FileNotFoundError that says nothing
    # about the capability it guards.
    module_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ledger", "event_frame.py")
    tree = ast.parse(open(module_path, encoding="utf-8").read())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    text = open(module_path, encoding="utf-8").read()

    assert not any(name.endswith((".store", ".gate")) for name in imports)
    assert "write_batch(" not in text
    assert ".commit(" not in text
    assert ".rollback(" not in text
    assert "atoms_from_ledger_frame" not in text


def test_a_bound_attribute_column_must_be_declared_like_every_other_bound_column():
    """🔴 이 라운드가 «발견»한 것. 검증기는 「프로파일이 바인드한 «모든» 컬럼은
    `map.input_columns` 에 있어야 한다」를 이미 강제하고, 속성 바인딩도 «그 규칙 안»이다.

    그래서 오늘 운영자는 이름을 «세 자리»에 적는다 — 엔티티의 목록 · 소스의 bind · 그리고
    `map.input_columns`. 판정 124 의 «두 줄»은 그 셋째 자리를 세지 않았다.

    ⚠️ 이 시험은 그것을 «옳다»고 말하지 않는다. 오늘 그렇다는 것을 «못 박을» 뿐이고,
    셋째 자리를 없애는 판정이 오면 이 시험이 그날 «빨개져서» 갱신을 부른다."""
    from ledger.setup_bundle import LedgerSetupValidationError

    raw = logical_bundle()
    raw["entities"]["InputEntity@1"]["attributes"] = ["product"]
    raw["sources"]["input_rows"]["bind"]["entities"] = {
        "InputEntity@1": {"attributes": {"product": {"kind": "column",
                                                     "column": "event_key"}}}}
    mapper = raw["sources"]["input_rows"]["map"]
    mapper["input_columns"] = [name for name in mapper["input_columns"]
                               if name != "event_key"]

    with pytest.raises(LedgerSetupValidationError) as caught:
        snapshot(raw)
    assert caught.value.path.endswith("map.input_columns")
    assert "event_key" in caught.value.message


def test_the_declared_column_is_then_selected_by_the_cursor():
    """셋째 자리를 적으면 커서가 읽는다 — 즉 오늘의 길은 «막혀 있지 않고», 다만 «한 자리 더»다."""
    raw = logical_bundle()
    raw["entities"]["InputEntity@1"]["attributes"] = ["product"]
    raw["sources"]["input_rows"]["bind"]["entities"] = {
        "InputEntity@1": {"attributes": {"product": {"kind": "column",
                                                     "column": "event_key"}}}}

    columns = base_select_columns_of(snapshot(raw), "input_rows")

    assert "event_key" in columns, columns


def test_a_source_binding_no_attribute_selects_exactly_what_it_always_did():
    """㉥ 무회귀 — 이 축은 «적은 선언에서만» 무언가를 한다."""
    plain = base_select_columns_of(snapshot(), "input_rows")

    assert plain == ("event_at", "event_key", "record_id", "row_id", "source_id", "target_id")
