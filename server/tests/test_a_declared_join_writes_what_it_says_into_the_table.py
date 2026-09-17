# -*- coding: utf-8 -*-
"""S-237. 통합 선언의 `join` 종류 — 선언 한 건이 «쓰는» 조인 규칙 «둘»이 된다.

🔴 THE GRAMMAR COULD BE WRITTEN AND COULD NOT RUN. `derive: {kind: "join"}` came out of the
translator with no mapper cell at all, so the loader refused it as `unresolvable_mapper` -
a declaration the product accepts on paper and drops on load. This file is the seat where
that stops being true.

🔴 THE READ-TIME VIRTUAL JOIN IS NOT TOUCHED, AND THAT IS ASSERTED, NOT PROMISED. Production
runs on it. `builtin:join` stays the read-time kind, `builtin:join_into` is the writing one,
and `register_builtin` refuses two claimants of one id - so the two cannot quietly become one.

⚠️ WHAT THIS FILE CANNOT SEE is whether the two paths AGREE on a real declaration. That is a
comparison against the box's live virtual join, value by value, and it is reported separately
- a fixture I wrote agreeing with itself is not evidence about the join an operator declared.
"""
import json
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import builtins, join_into, rule_shape                  # noqa: E402
from chain import ingestion_worker as worker                       # noqa: E402
from database.database import Base                                 # noqa: E402
from database import crud, models, schemas                         # noqa: E402

LEFT = "s237_left_log"
RIGHT = "s237_right_attribution"

TABLES = {
    LEFT: {
        "business_key": "log_key",
        "composite_key_source": ["log_key"],
        "column_types": {"log_key": "string", "job": "string",
                         "lot_confirmed": "string", "note": "string"},
        "display_columns": ["log_key", "job", "lot_confirmed", "note"],
    },
    RIGHT: {
        "business_key": "job",
        "composite_key_source": ["job"],
        "column_types": {"job": "string", "lot": "string"},
        "display_columns": ["job", "lot"],
    },
}

#: The declaration an operator writes, WHOLE. No `fold` (판정 397 - it is computed from the two
#: tables) and no `on.columns` (판정 398 - the shell derives it from the join key).
DECLARATION = {
    "name": "s237_lot_from_attribution",
    "on": {"table": LEFT},
    "derive": {"kind": "join",
               "join": {"right_table": RIGHT,
                        "on": [{"left": "job", "right": "job"}],
                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
    "into": {"table": LEFT},
}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _push(db, table, rows):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(row), source_name="seed",
                                  updated_by="s237") for row in rows]))


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _rule(**over):
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION))
    rule.update(over)
    return rule


# ---------------------------------------------------------------------------
# 🔴 ⓐ — one declaration, two rules, read by the REAL loader
# ---------------------------------------------------------------------------

@pytest.fixture(name="load")
def fixture_load(tmp_path, monkeypatch):
    """⛔ SYNTHESIZED RULES ARE HELD OUT so the subject is the LOADER and not this box's live
    enrichment and virtual-join declarations."""
    from chain import builtins as chain_builtins

    monkeypatch.setattr(chain_builtins, "synthesize_chain_rules", lambda **kwargs: [])

    def run(declarations):
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": declarations}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        return worker.load_chain_rules()

    return run


def test_one_declared_join_becomes_two_rules_that_watch_both_tables(load):
    """🔴 A RULE WATCHES ONE `trigger_table`, AND A JOIN HAS TO BE RECOMPUTED FROM TWO SIDES.
    So the shell hands the loader both - carrying the SAME `params`, which is what makes this
    one declaration with two triggers rather than two declarations to keep in step."""
    kept = load([DECLARATION])
    mine = [r for r in kept if str(r.get("name") or "").startswith(DECLARATION["name"])]

    by_name = {r["name"]: r for r in mine}
    reference = DECLARATION["name"] + rule_shape.REFERENCE_SUFFIX
    assert sorted(by_name) == sorted([DECLARATION["name"], reference])
    assert by_name[DECLARATION["name"]]["trigger_table"] == LEFT
    assert by_name[reference]["trigger_table"] == RIGHT
    assert {r["target_table"] for r in mine} == {LEFT}
    assert {r["mapper"] for r in mine} == {join_into.JOIN_INTO_MAPPER}
    assert by_name[DECLARATION["name"]]["params"] == by_name[reference]["params"], (
        "one spec, two triggers")
    # 🔴 AND THE ORDER IS THE WALK'S ANSWER: producer before consumer. The reference
    # rule writes the table the target rule triggers on, so `rule_order` puts it first.
    #
    # ⚰️ THIS PINNED FILE ORDER UNTIL S-278, on the reasoning that a `follow_up` rule
    # never shares a trigger group with the left rule so 「before」 had no operational
    # content - and that the edge read as a phantom cycle of one edge that cannot fire.
    # The owner ruled on 2026-09-16 that a join runs like any other chain rule, so both
    # halves are on the trigger path now: the edge FIRES, 「before」 means what it says,
    # and the walk orders them. Measured with the ordering walk on this shape: no cycle
    # is reported.
    assert [r["name"] for r in mine] == [reference, DECLARATION["name"]], (
        "the reference half writes what the target half triggers on, so it is ordered "
        "first - producer before consumer")


def test_the_loader_no_longer_refuses_a_join_as_an_unrunnable_mapper(load):
    """⚰️ THIS IS THE DEFECT. `builtin:` kinds were reachable only from SYNTHESIZED rules,
    which skip the grammar check by design; a unified declaration lives in the operator's
    file, so it goes through the check and was dropped as `unresolvable_mapper`."""
    assert [r["name"] for r in load([DECLARATION])
            if r.get("name") == DECLARATION["name"]] == [DECLARATION["name"]]


def test_both_rules_run_on_the_trigger_path(load):
    """🔴 [S-278, 소유자 2026-09-16] A JOIN RUNS LIKE ANY OTHER CHAIN RULE. Both halves
    are woken by the outbox event for a write to the table they watch - the same door every
    mapper comes through.

    ⚰️ THIS ASSERTED `follow_up: True` ON BOTH, on 「요청·커밋 경로 인라인 금지」 and
    S-151's 70,800-row reach. That number is about how far ONE reference row goes and it
    stands; which lap the work belongs on is a different question, and the owner answered
    it. The paced lane keeps its other kinds.

    ⚠️ WHAT MAKES IT SAFE IS ASSERTED SEPARATELY, in
    `test_a_join_runs_on_the_trigger_path_like_any_mapper`: a join declares no
    `allow_chain_trigger`, so the rows it writes cannot wake it again."""
    mine = [r for r in load([DECLARATION])
            if str(r.get("name") or "").startswith(DECLARATION["name"])]

    assert [r.get("follow_up") for r in mine] == [None, None]
    assert not any("allow_chain_trigger" in r for r in mine), (
        "a join that opted into chain-produced events would feed itself")
    assert all(r["mapper"] in builtins.BUILTIN_KINDS for r in mine), (
        "the dispatcher only reaches rules whose mapper is in the table")


# ---------------------------------------------------------------------------
# 🔴 ⓑ — what it writes, and what it deliberately does not
# ---------------------------------------------------------------------------

def test_the_group_path_actually_calls_the_join(db, caplog):
    """🔴 [S-278 후반] THE ASSERTION THAT WAS MISSING, AND ITS ABSENCE IS THE WHOLE STORY.
    Every other gate in this round asked the DISPATCHER'S PREDICATE - 「does this event
    reach this rule」 - and none asked 「and then what CALLS it」. Taking the join off the
    paced lap took it off the only lap that had a `builtin:` dispatcher at all: the group
    path reads `mapper_module`/`mapper_function`, which a builtin rule does not carry, so
    it reached `execute_custom_mapper(None, None, ...)` and raised
    `'NoneType' object has no attribute 'startswith'`. Measured, not imagined.

    ⛔ SO THIS DRIVES THE WRITE, NOT THE PREDICATE. It runs the real group function and
    asserts the VALUE arrived and that the layer it arrived under is the chain's.
    「착지는 배선이 아니다」 - this is the wiring.
    """
    import logging

    from chain import cell_layer

    _push(db, RIGHT, [{"job": "J-GROUP", "lot": "LOT-GROUP"}])
    _push(db, LEFT, [{"log_key": "L-GROUP", "job": "J-GROUP"}])
    db.commit()

    # ⚠️ THE REAL OUTBOX ROWS, NOT A DOUBLE. The group path expands events through
    # `outbox_expand`, keyed by `event_uuid`; a fake would let this pass while the real
    # payload shape failed, which is the class of green this round is already full of.
    events = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).all()
    assert events, "the seed wrote no outbox event, so this proves nothing"

    stood = rule_shape.expand_declaration(DECLARATION, crud.TABLE_CONFIG)[0]
    caplog.clear()
    with caplog.at_level(logging.INFO):
        worker._process_chain_transaction_group_sync("tx-s278", events, db, stood)

    assert [r.lot_confirmed for r in _rows(db, LEFT)] == ["LOT-GROUP"], (
        "the group path did not call the join at all")
    layers = {s.source_name for s in db.query(models.CellSource).filter(
        models.CellSource.table_name == LEFT,
        models.CellSource.column_name == "lot_confirmed").all()}
    assert cell_layer.R1_SOURCE_NAME in layers, layers
    # 🔴 [S-279] THE LINE'S AUTHOR IS THE SEAT NOW, and the count still has to be on it. The
    #    prefix moved from `[ChainBuiltin]` to one spelling shared with a file mapper -
    #    「로그도 «문»이다」 - so what is asserted is the COUNT, which is the thing an operator
    #    staring at a long group needs and the thing that would silently vanish.
    from chain import rule_run

    said = [r.getMessage() for r in caplog.records
            if ("[%s]" % rule_run.RULE_LOG_TAG) in r.getMessage()]
    # 🔴 [판정 562] THE CELL MOVED AND THE COUNT DID NOT. This asked for `written=1`,
    #   which is 「rows the rule wrote FOR ITSELF」 - and the join no longer does: it is a
    #   mapper now, so it PROPOSES and the caller's batch writes. The row is still
    #   written (the batch line says size: 1) and the count an operator reads is
    #   `rows_out`, which is what this now pins.
    # ⚠️ IF BOTH WERE ACCEPTED HERE the assertion would pass for a join that wrote
    #   nothing at all, so it names ONE cell.
    assert said and "rows_out=1" in said[0], (
        "the count the paced lap used to publish must not vanish with the lap")


def test_the_group_paths_join_write_makes_ONE_event_not_one_per_row(db):
    """🔴 [S-278 A] THE DISCRIMINANT NEEDS MORE THAN ONE ROW, which is why it is its own
    test. With a single row 「collapsed」 and 「one per row」 produce the same count, and a
    fixture both rules agree on decides nothing.

    ⛔ THE DEFECT THIS STANDS IN FRONT OF IS RECORDED IN THIS REPOSITORY (S-249 ⓔ-1): a
    builtin writing per-row events turned 1,000 follow-up writes into 「1,000 outbox
    events, 1,000 queue items, 1,000 laps and 1,000 lines」 - the owner's 「한 행당 로그
    하나」. The follow-up lap wraps its builtin call in `outbox_mode(COLLAPSED)` for
    exactly that reason, and the group path's own collapse scope wraps the MAPPER branch's
    `apply_batch_updates`, not a builtin that writes for itself.
    """
    from database.context import outbox_mode          # noqa: F401  (documents the scope)

    _push(db, RIGHT, [{"job": "J-MANY", "lot": "LOT-MANY"}])
    _push(db, LEFT, [{"log_key": "L-M%d" % n, "job": "J-MANY"} for n in range(5)])
    db.commit()
    before = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).count()

    events = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).all()
    stood = rule_shape.expand_declaration(DECLARATION, crud.TABLE_CONFIG)[0]
    worker._process_chain_transaction_group_sync("tx-s278-many", events, db, stood)

    assert [r.lot_confirmed for r in _rows(db, LEFT)] == ["LOT-MANY"] * 5
    made = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).count() - before
    assert made == 1, (
        "the join wrote 5 rows and produced %d outbox events - one per row is the shape "
        "S-249 removed from the follow-up lap" % made)


def test_a_matched_row_gets_the_right_tables_value(db):
    _push(db, RIGHT, [{"job": "J1", "lot": "LOT-1"}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1"}])
    left_ids = [r.row_id for r in _rows(db, LEFT)]

    result = join_into.run(db, _rule(), row_ids=left_ids)

    assert result["written"] == 1 and result["side"] == "target"
    assert [r.lot_confirmed for r in _rows(db, LEFT)] == ["LOT-1"]


def test_a_matched_null_is_written_as_null_and_an_unmatched_row_is_left_alone(db):
    """🔴 THE TWO LOOK THE SAME IN THE RESULT SET AND GET OPPOSITE TREATMENT. 「the right row
    exists and says the value is empty」 is an ANSWER, and refusing to write it leaves a stale
    value standing where the declaration says there is none. 「no right row」 is not an answer,
    and writing NULL for it would erase a value this join never spoke about."""
    _push(db, RIGHT, [{"job": "J_EMPTY", "lot": None}])
    _push(db, LEFT, [{"log_key": "L_MATCHED", "job": "J_EMPTY",
                      "lot_confirmed": "STALE"},
                     {"log_key": "L_UNMATCHED", "job": "J_ABSENT",
                      "lot_confirmed": "KEEP"}])
    left_ids = [r.row_id for r in _rows(db, LEFT)]

    result = join_into.run(db, _rule(), row_ids=left_ids)

    by_key = {r.log_key: r.lot_confirmed for r in _rows(db, LEFT)}
    assert result["written"] == 1, "only the matched row was written"
    assert by_key["L_MATCHED"] is None, "a matched null erases the stale value"
    assert by_key["L_UNMATCHED"] == "KEEP", "an unmatched row is not spoken about"


def test_the_reference_side_recomputes_the_left_rows_that_point_at_it(db):
    """⚠️ ONLY THE `WHERE` DIFFERS, which is why this is one kind and not two. The side is
    read from the DECLARATION (`trigger_table` against `right_table`), so a caller cannot put
    a rule on the wrong side by handing it the wrong argument."""
    _push(db, RIGHT, [{"job": "J1", "lot": "OLD"}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1"}, {"log_key": "L2", "job": "J2"}])
    join_into.run(db, _rule(), row_ids=[r.row_id for r in _rows(db, LEFT)])

    right = _rows(db, RIGHT)[0]
    _push(db, RIGHT, [{"job": "J1", "lot": "NEW"}])
    result = join_into.run(db, _rule(trigger_table=RIGHT), row_ids=[right.row_id])

    assert result["side"] == "reference"
    by_key = {r.log_key: r.lot_confirmed for r in _rows(db, LEFT)}
    assert by_key["L1"] == "NEW", "the row pointing at the changed reference was recomputed"
    assert by_key["L2"] is None, "a row pointing elsewhere was not touched"


def test_the_written_layer_is_the_rules_own_name(db, monkeypatch):
    """🔴 LAYERING ASKS 「WHO WROTE THIS CELL」, and 「the chain」 is not an answer an operator
    can act on when three declarations write one table.

    ⚠️ SCORED AT THE WRITE DOOR, not by reading the layer back: how a layer is stored is
    `crud`'s subject and has its own tests, while what THIS module hands it is this file's.
    A test that skipped when it could not find a reader would be a test that never runs."""
    seen = []
    real = crud.apply_batch_updates
    monkeypatch.setattr(crud, "apply_batch_updates",
                        lambda db_, table, batch, *a, **k: (seen.append(batch),
                                                            real(db_, table, batch, *a, **k))[1])
    _push(db, RIGHT, [{"job": "J1", "lot": "LOT-1"}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1"}])
    seen.clear()
    join_into.run(db, _rule(), row_ids=[r.row_id for r in _rows(db, LEFT)])

    # The LAYER is the chain's (so the wake filter treats this write like every other
    # chain write) and the AUTHOR is the rule's (so an operator can still see who wrote it).
    assert seen and seen[0].updates[0].source_name == join_into.CHAIN_LAYER
    assert seen[0].updates[0].updated_by == DECLARATION["name"]


def test_a_rule_that_cannot_run_says_why_rather_than_writing_nothing_quietly(db):
    """⛔ A JOIN THAT SITS ENABLED AND WRITES NOTHING IS INDISTINGUISHABLE FROM ONE THAT HAD
    NOTHING TO WRITE, which is the silence every refusal in this product exists to break."""
    _push(db, LEFT, [{"log_key": "L1", "job": "J1"}])
    ids = [r.row_id for r in _rows(db, LEFT)]
    broken = _rule()
    broken["params"] = dict(broken["params"], right_table="s237_no_such_table")

    result = join_into.run(db, broken, row_ids=ids)

    assert result["written"] == 0
    assert "s237_no_such_table" in result["refusal"]


# ---------------------------------------------------------------------------
# 🔴 ⓒ — the folded key, and the id that was already taken
# ---------------------------------------------------------------------------

def test_the_fold_is_computed_from_the_two_tables_and_never_authored(db, monkeypatch):
    """🔴 [판정 397] THE JOIN DOES NOT GET TO DECLARE ITS OWN FOLD. Folding is derived from
    the two TABLES' notation declarations, and the unique index is built from the same source
    - so a fold authored on the join would be a second author of one fact, free to disagree
    with the index expression. This asserts the mapper ASKS the shared function, with the
    tables and columns it is joining.

    ⚠️ 「EITHER SIDE DECLARED」 MEANS BOTH SIDES FOLDED, and that rule lives in the shared
    function: a join folded on one side silently drops matches the unfolded join was making.
    """
    import notation_norm

    asked = []

    def spy(left_table, left_column, right_table, right_column):
        asked.append((left_table, left_column, right_table, right_column))
        return None

    monkeypatch.setattr(notation_norm, "join_pair_rules", spy)
    _push(db, RIGHT, [{"job": "J1", "lot": "LOT-1"}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1"}])

    join_into.run(db, _rule(), row_ids=[r.row_id for r in _rows(db, LEFT)])

    assert (LEFT, "job", RIGHT, "job") in asked, (
        "the fold was not asked for by TABLE and column - the join is authoring it")
    # ⚠️ WHAT THIS DOES NOT ASSERT, and why: whether the folded SQL matches on this dialect
    # is the shared function's own subject (it needs the fold scalar installed per dialect),
    # and `test_notation_normalization` owns it. Asserting it here would score that function
    # twice and leave 「did this join ASK」 - the thing 판정 397 is about - unscored.


def test_a_key_declared_normalized_on_one_side_folds_on_both(db, monkeypatch):
    """🔴 THE FOLDED EXPRESSION IS THE MATCH, and without it these two rows do not meet.
    `J_1` and `J-1` are one key under separator folding and two keys without it - so a join
    that dropped the fold would go on returning 「no match」 for rows an operator can see are
    the same, with nothing red anywhere.

    ⚠️ DECLARED ON THE LEFT ONLY, deliberately: 「either side declared means BOTH sides
    folded」 is the rule the shared function owns, and a join folded on one side silently drops
    matches the unfolded join was already making."""
    import notation_norm

    notation_norm.install_sqlite_fold()
    monkeypatch.setattr(notation_norm, "normalized_by_table",
                        lambda: {LEFT: {"job": {"rules": {notation_norm.RULE_SEPARATOR: True}}}})
    _push(db, RIGHT, [{"job": "J-1", "lot": "LOT-1"}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J_1"}])

    result = join_into.run(db, _rule(), row_ids=[r.row_id for r in _rows(db, LEFT)])

    assert result["written"] == 1, "the two spellings of one key did not fold onto each other"
    assert [r.lot_confirmed for r in _rows(db, LEFT)] == ["LOT-1"]


def test_the_join_declares_no_fold_cell_at_all(db):
    """⚰️ A CELL THAT WAS PROPOSED AND TAKEN OUT (판정 397). `fold` is not among the sub-cells
    this product reads, so an author writing one is told its name rather than being given a
    second, silently divergent way to spell the key."""
    assert "fold" not in join_into.JOIN_CELLS
    assert join_into.unknown_cells({"right_table": RIGHT, "on": [], "fold": []}) == ["fold"]


# ---------------------------------------------------------------------------
# 🔴 ⓓ — the join is written ONCE and the trigger follows it (판정 398)
# ---------------------------------------------------------------------------

def test_the_trigger_columns_are_derived_from_the_left_join_key(load):
    """🔴 ONE VALUE, ONE PLACE. The left join key IS the trigger column - true by coincidence
    in every virtual join declared today, and this grammar says it instead of leaving the next
    author to rediscover it."""
    mine = [r for r in load([DECLARATION])
            if str(r.get("name") or "").startswith(DECLARATION["name"])]

    assert [r.get("trigger_columns") for r in mine] == [["job"], ["job"]]


def test_writing_the_trigger_columns_as_well_is_allowed_while_they_agree(load):
    """⚠️ SAYING ONE THING TWICE IS REDUNDANT, NOT WRONG. Refusing agreement would drop
    declarations that are correct."""
    agreeing = dict(DECLARATION, name="s237_agreeing",
                    on={"table": LEFT, "columns": ["job"]})

    assert [r["name"] for r in load([agreeing])
            if r["name"] == "s237_agreeing"] == ["s237_agreeing"]


def test_a_trigger_column_that_disagrees_with_the_join_is_refused_by_name(load, caplog):
    """⛔ TWO ANSWERS TO 「WHICH COLUMNS WAKE THIS JOIN」. Picking one silently is how a join
    comes to watch a column nobody asked it to watch - and the OTHER declarations in the file
    are not at fault, so one rule is dropped, not the load."""
    import logging

    conflicting = dict(DECLARATION, name="s237_conflicting",
                       on={"table": LEFT, "columns": ["note"]})
    with caplog.at_level(logging.ERROR):
        kept = load([conflicting, dict(DECLARATION)])

    names = [r.get("name") for r in kept]
    assert "s237_conflicting" not in names
    assert DECLARATION["name"] in names, "the innocent declaration still loaded"
    said = " ".join(record.getMessage() for record in caplog.records)
    assert "join_trigger_conflict" in said and "s237_conflicting" in said, said


def test_a_join_cell_nobody_reads_is_named_and_the_rule_still_runs(load, caplog):
    """⚠️ YESTERDAY'S POSTURE, UNCHANGED. A cell the product does not know may be a live
    argument it has not learned yet; refusing it would stop a declaration that works."""
    import logging

    odd = dict(DECLARATION, name="s237_odd_cell")
    odd["derive"] = {"kind": "join",
                     "join": dict(DECLARATION["derive"]["join"], wobble=1)}
    with caplog.at_level(logging.WARNING):
        kept = load([odd])

    assert "s237_odd_cell" in [r.get("name") for r in kept], "the rule still runs"
    assert "wobble" in " ".join(r.getMessage() for r in caplog.records)


def test_the_two_write_join_doors_keep_separate_ids():
    """⛔ `builtin:join` IS TAKEN - by the LEGACY DECLARATION's join, which WRITES too.
    ⚰️ This test was called `..._the_read_time_join_keeps_its_own_id` and said production
    ran on it; ruling 461 deleted the read-time executor and the owner ruled that production
    writes into the table. What the two ids actually separate is which declaration file
    birthed the rule (판정 461 ③ - two write doors, and that is the debt).
    `register_builtin` refuses a second claimant by name, so this is enforced not remembered."""
    from chain import legacy_join_declaration as vjc

    assert join_into.JOIN_INTO_MAPPER != vjc.JOIN_MAPPER
    assert builtins.BUILTIN_KINDS[vjc.JOIN_MAPPER] is not join_into.run
    with pytest.raises(builtins.UnknownBuiltinKind):
        builtins.register_builtin(vjc.JOIN_MAPPER, join_into.run, builtins.HANDS_ROW_IDS)


def test_this_module_does_not_borrow_the_other_doors_engine():
    """🔴 BORROW THE FUNCTION, NOT THE ENGINE (the ruling's words). The fold has to be shared
    or the two write doors would disagree about the key; the other door's engine, its caches
    and its declaration loader are deliberately not in this path.

    ⚰️ THIS GUARD NAMED A PACKAGE THAT NO LONGER EXISTS. It forbade importing `virtual_join`,
    which ruling 461 deleted - so from that commit it could not go red for anything, while the
    engine that actually survived (`chain.legacy_materialized_join`, the second write door)
    was unguarded. A guard whose subject was deleted scores 「no problem」, not 「no defect」."""
    import inspect

    body = inspect.getsource(join_into)
    # ⚠️ IMPORTS, NOT MENTIONS. The module NAMES the other door in prose - that is the point
    # of the prose - so a substring check would score the docstring instead of the dependency
    # and would go red for explaining itself.
    imports = [line.strip() for line in body.splitlines()
               if line.strip().startswith(("import ", "from "))]
    borrowed = [line for line in imports
                if "legacy_materialized_join" in line or "legacy_join_declaration" in line]
    assert not borrowed, borrowed
    assert [line for line in imports if "notation_norm" in line], (
        "the shared fold is what keeps the two joins' keys from drifting")


# ---------------------------------------------------------------------------
# 2026-09-15 - two answers for one left row: neither is written (found at migration time)
# The catalogue gate (narrow key / no unique index) is NOT here on purpose: it would import
# virtual_join, and the test above forbids that so the key has one author. The row-level
# net below is what protects the write; it needs no catalogue and no second author.
# ---------------------------------------------------------------------------

def test_a_left_row_with_two_right_answers_is_skipped_by_name_and_the_rest_are_written():
    """The row-level net (principle 2). Two answers for one left row means neither is the
    answer; that row is skipped by name and every other row is still written.

    🔴 [판정 567] ASKED OF THE SEAT THAT BUILDS THE ITEMS, not of the one that writes
    them. The net lives in `_update_items` now, which is also the body the dynamic mapper
    carries - so this scores the net on BOTH doors instead of only the writing one. The
    stand-in for `apply_batch_updates` is gone with the write: nothing to intercept.
    """

    class Row:
        # ⚠️ [S-280] `origin_row_id` IS PART OF THE SHAPE `_answer` RETURNS, so this stand-in
        # carries it. A fixture that hand-builds the row the code reads is the second author
        # of that shape, and one that lags it tests a row the SELECT no longer produces.
        def __init__(self, rid, matched, v, origin="ref_row"):
            self._mapping = {"row_id": rid, "matched": matched, "take_0": v,
                             "origin_row_id": origin if matched else None}
            self.matched = matched
    rows = [Row("fan", True, "A"), Row("fan", True, "B"), Row("ok", True, "C"),
            Row("miss", False, None)]
    spec = {"right_table": "right_t", "on": [{"left": "k", "right": "k"}], "take": ["v"]}

    items = join_into._update_items(None, "left_t", rows, spec, "rule_x")

    assert len(items) == 1
    assert [i.row_id for i in items] == ["ok"]
    assert items[0].updates == {"v": "C"}
# ---------------------------------------------------------------------------
# 2026-09-15 - a numeric join key is folded by the machine, not refused by the database
# ---------------------------------------------------------------------------

def test_a_number_key_is_compared_as_text_and_a_text_key_is_left_alone():
    """Owner, migrating a live join: 「double precision 자료형 오류」. The fold said
    `coalesce(col, '')` to a Float column and PostgreSQL refused the '' - the operator had
    declared a join and lost it to a type they never chose. Scored on the SQL this module
    EMITS for PostgreSQL, because SQLite accepts what PostgreSQL refuses."""
    from sqlalchemy import Column, Float, MetaData, String, Table
    from sqlalchemy.dialects import postgresql

    t = Table("t", MetaData(), Column("num", Float), Column("txt", String))
    num_sql = str(join_into._folded(t.c.num, None).compile(dialect=postgresql.dialect()))
    txt_sql = str(join_into._folded(t.c.txt, None).compile(dialect=postgresql.dialect()))
    # 🔴 [S-245] THE SPELLING MOVED FROM `CAST(... AS TEXT)` TO `::text`, AND THAT IS THE
    # POINT, NOT A DETAIL. This seat cast in a spelling the INDEX COMPARATOR cannot see:
    # `virtual_join.config.normalize_index_expression` strips `::text` as noise PostgreSQL
    # adds when it renders an index definition, and leaves `CAST(...)` standing. So the
    # write-time join and the index that has to serve it were casting in two shapes, and
    # only one of them normalises to what the other seats require.
    assert "t.num::text" in num_sql, num_sql
    assert txt_sql == "coalesce(t.txt, %(coalesce_1)s)", txt_sql
