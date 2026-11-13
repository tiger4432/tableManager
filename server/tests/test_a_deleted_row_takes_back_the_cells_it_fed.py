# -*- coding: utf-8 -*-
"""S-280 · 판정 434·435. A cell records which row fed it, so that row's deletion withdraws it.

🔴 WHAT WAS WRONG WAS NOT A MISSING CALL, IT WAS A MISSING FACT. A chain rule reads some
other row and writes a cell from it, and nothing anywhere recorded that the two were
connected. So when the reference row was deleted the cell stood, and no amount of wiring
could have fixed it: the deleted row cannot be re-read, and the product's delete doors
(`crud.delete_rows_batch`, `crud.purge_map_rows`) stage a COLLAPSED outbox event carrying
row ids and NO values. There was nothing left to work the connection out FROM.

⚠️ THE MECHANISM THAT LOOKED LIKE THE ANSWER DID NOT WORK EITHER. `retract_rows` had no
caller, and had it been called it passed neither `row_ids` nor `apply` to
`withdraw_source` - whose defaults are 「the whole table」 and 「roll back」. So it would have
written nothing, and on the day somebody passed `apply` it would have taken every row. Its
own test was green throughout, because it asserted the three arguments it named and let a
`**k` swallow the two that decide whether anything happens.

🔴 THE UNIT IS THE CELL, AND THAT IS WHY THIS SERVES EVERY KIND. A note taken per KEY needs
somebody to resolve 「key -> cells」, and only a join can do that. A note taken per cell needs
no translation at all: `withdraw_source` already works one cell at a time, and a writer
knows its own input at the moment it writes, whatever it computed on the way.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import cell_layer, join_into, rule_run, synthesis# noqa: E402
from conftest import run_join_and_write                        # noqa: E402
from database.database import Base                                        # noqa: E402
from database import crud, models, schemas                                # noqa: E402

TARGET = "s280_target"
REF = "s280_reference"
TABLES = {
    TARGET: {
        "business_key": "part_no",
        "composite_key_source": ["part_no"],
        "column_types": {"part_no": "string", "ref_key": "string", "grade": "string"},
        "display_columns": ["part_no", "ref_key", "grade"],
    },
    REF: {
        "business_key": "ref_key",
        "composite_key_source": ["ref_key"],
        "column_types": {"ref_key": "string", "grade": "string"},
        "display_columns": ["ref_key", "grade"],
    },
}

RULE = {
    "name": "s280_join",
    "enabled": True,
    "trigger_table": TARGET,
    "target_table": TARGET,
    "mapper": join_into.JOIN_INTO_MAPPER,
    "params": {
        "right_table": REF,
        "on": [{"left": "ref_key", "right": "ref_key"}],
        "take": [{"from": "grade", "into": "grade"}],
    },
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


def _write(db, table, values):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(values), source_name="seed",
                                  updated_by="s280")]))
    db.commit()
    key = TABLES[table]["business_key"]
    return db.query(models.DYNAMIC_TABLES[table]).filter_by(
        business_key_val=values[key]).one().row_id


def _chain_cells(db, column="grade"):
    """The chain's claims on the target, as `{row_id: origin_row_id}` - its row layers too (the product's predicate)."""
    from chain import cell_layer

    return {row_id: line["input_row"] for row_id, _col, line in _claimed(db, TARGET, join_into.CHAIN_LAYER, [column])}


# ---------------------------------------------------------------------------
# 🔴 판정 433 ③'s fixture, end to end
# ---------------------------------------------------------------------------

def test_the_cell_a_deleted_reference_row_fed_is_withdrawn(db):
    """🔴 THE ASSERTION THE ROUND EXISTS FOR, and it is RED before the stamp: the reference
    row is deleted and the value it supplied keeps standing in the target, indistinguishable
    from a value somebody measured."""
    ref_row_id = _write(db, REF, {"ref_key": "K-1", "grade": "A"})
    target_row_id = _write(db, TARGET, {"part_no": "P-1", "ref_key": "K-1"})

    run_join_and_write(db, RULE, row_ids=[target_row_id])
    db.commit()

    assert _chain_cells(db) == {target_row_id: ref_row_id}, (
        "the join did not write the cell, or wrote it without saying which row it read - "
        "either way what follows would prove nothing")

    crud.delete_rows_batch(db, REF, [ref_row_id], "tester")
    db.commit()

    cell_layer.withdraw_by_origin(db, [ref_row_id], apply=True)
    db.commit()

    assert _chain_cells(db) == {}, (
        "the reference row is gone and the cell it fed is still standing")


def test_a_sibling_cell_fed_by_another_row_is_left_alone(db):
    """⛔ THE FAILURE MODE OF A RETRACTION IS TAKING TOO MUCH, and it is silent. Narrowing by
    the source NAME alone would take every chain write on the table - `join_into` writes
    under the shared `chain_ingestion` channel by the owner's own ruling - so the stamp has
    to be what decides, cell by cell."""
    kept_ref = _write(db, REF, {"ref_key": "K-keep", "grade": "A"})
    gone_ref = _write(db, REF, {"ref_key": "K-gone", "grade": "B"})
    kept = _write(db, TARGET, {"part_no": "P-keep", "ref_key": "K-keep"})
    doomed = _write(db, TARGET, {"part_no": "P-gone", "ref_key": "K-gone"})

    run_join_and_write(db, RULE, row_ids=[kept, doomed])
    db.commit()
    assert _chain_cells(db) == {kept: kept_ref, doomed: gone_ref}

    crud.delete_rows_batch(db, REF, [gone_ref], "tester")
    cell_layer.withdraw_by_origin(db, [gone_ref], apply=True)
    db.commit()

    assert _chain_cells(db) == {kept: kept_ref}, (
        "the withdrawal was aimed at the deleted row's cells and took a sibling's too")


def test_a_dry_run_writes_nothing(db):
    """⚠️ `apply` DEFAULTS TO FALSE ON `withdraw_source`, which is exactly how `retract_rows`
    came to be an inert function with a name that promised otherwise. It stays false-by-
    default there; what this asserts is that the default still MEANS 「do not write」 when it
    arrives through the new road, so the one caller that passes True is the only one acting.
    """
    ref_row_id = _write(db, REF, {"ref_key": "K-1", "grade": "A"})
    target_row_id = _write(db, TARGET, {"part_no": "P-1", "ref_key": "K-1"})
    run_join_and_write(db, RULE, row_ids=[target_row_id])
    db.commit()

    cell_layer.withdraw_by_origin(db, [ref_row_id])
    db.commit()

    assert _chain_cells(db) == {target_row_id: ref_row_id}, (
        "a dry run withdrew the cell, so nothing distinguishes previewing from doing")


def _layer(db, part_no, column, source, value, origin):
    """One layer written through the door - its line carries `origin` as its input row."""
    crud.apply_batch_updates(db, TARGET, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"part_no": part_no, column: value}, source_name=source, updated_by="s280",
        origin_row_id=origin)]))
    db.commit()


def test_a_shared_layer_name_takes_only_the_cells_the_deleted_row_stamped(db):
    """🔴 [총괄 10-07 ②] THE STAMP, NOT (COLUMNS x ROWS) OF A NAME. O1 fed (P-1, grade) and (P-2,
    ref_key), O2 fed (P-2, grade), all under the one name `chain_ingestion`. A per-name group
    of O1 is {grade, ref_key} x {P-1, P-2}, which names (P-2, grade) - O2's cell."""
    rows = [_write(db, TARGET, {"part_no": p}) for p in ("P-1", "P-2")]
    for part_no, column, origin in (("P-1", "grade", "O1"), ("P-2", "ref_key", "O1"), ("P-2", "grade", "O2")):
        _layer(db, part_no, column, join_into.CHAIN_LAYER, "v", origin)
    assert _chain_cells(db) == {rows[0]: "O1", rows[1]: "O2"}, "canary: both grades are the chain's"

    cell_layer.withdraw_by_origin(db, ["O1"], apply=True)
    db.commit()

    assert _chain_cells(db) == {rows[1]: "O2"}, "another row's cell under the same name was taken"


# 총괄 10-07 ① — one pass per table, so a cell two withdrawn layers claim gives them up in turn.
# (source, value) written in this order - the newest shows. Layers are withdrawn in name order.
LAYERS = [("seed", "Z"), ("s_b", "B"), ("s_a", "A")]
TWO_LAYER_CASES = {
    # case: (apply, pinned layer, layers left, shown, cells withdrawn) - s_a's and s_b's lines say grade only: their
    # part_no repeats what seed's file layer says, and a file's repeat is no line (b025e2837, crud.file_layer_fold)
    "apply": (True, None, ["seed"], "Z", 2),
    "apply, s_a pinned": (True, "s_a", ["s_a", "seed"], "A", 1),
    "dry-run": (False, None, ["s_a", "s_b", "seed"], "A", 2),
}


@pytest.mark.parametrize("case", sorted(TWO_LAYER_CASES))
def test_a_cell_two_withdrawn_layers_claim_gives_up_each_in_turn(db, case):
    """The audit carries no values since the overhaul (owner 11-10): what the old «A -> B -> Z» audit
    lines kept is asserted on the lines - the withdrawn layers' values stay there as history, and the
    cell shows what the survivors decide - and the audit keeps one batch row a withdrawal that wrote."""
    from sqlalchemy import text

    from database import lines

    apply, pinned, left, shown, withdrawn = TWO_LAYER_CASES[case]
    row_id = _write(db, TARGET, {"part_no": "P-1"})
    for source, value in LAYERS:
        _layer(db, "P-1", "grade", source, value, None if source == "seed" else "origin-" + source)
    if pinned:
        db.add(models.CellOverwrite(table_name=TARGET, row_id=row_id, column_name="grade",
                                    is_overwrite=True, updated_by="t", manual_priority_source=pinned))
        db.commit()
    assert sorted(lines.layers(db, TARGET, [row_id], {"grade"})[(row_id, "grade")]) == ["s_a", "s_b", "seed"], \
        "canary: three layers stand on the cell"
    batches = db.query(lines.AuditBatch).count()

    stats = cell_layer.withdraw_by_origin(db, ["origin-s_a", "origin-s_b"], apply=apply)
    db.commit()

    assert stats["cells_withdrawn"] == withdrawn
    assert sorted(lines.layers(db, TARGET, [row_id], {"grade"}).get((row_id, "grade"), {})) == left
    assert db.query(models.DYNAMIC_TABLES[TARGET]).filter_by(row_id=row_id).one().grade == shown, (
        "the second layer was resolved against what was there before the first one left")
    kept = {src: v for src, v in db.execute(text(
        f'SELECT source_name, "{lines.value_column("grade")}" FROM "{lines.lines_relation(TARGET)}" '
        "WHERE row_id = :r AND source_name IN ('s_a', 's_b')"), {"r": row_id}) if v is not None}
    assert kept == {"s_a": "A", "s_b": "B"}, "a withdrawn layer's value stays in the lines as history"
    assert (db.query(lines.AuditBatch).count() > batches) == apply, \
        "a withdrawal that wrote lines leaves its batch row; a dry run leaves none"


# ---------------------------------------------------------------------------
# 판정 434 ④ — a kind with no correspondent answers BY NAME
# ---------------------------------------------------------------------------

def test_a_kind_that_cannot_be_reverted_says_so_by_name():
    """🔴 [판정 434 ④] 「조용한 0 금지」. `auto_confirm` answers from a candidate probe over a
    reference view, not from one reference row, so there is no single row to write down - and
    the note's NULL cannot carry 「이 종류는 못 한다」 because NULL already means 「stamped
    before this column existed」. Two facts under one spelling is the defect this whole round
    is about, so the seat says the second one out loud."""
    from chain import enrichment

    said = rule_run.retraction_refusal(
        {"name": "sweep", "mapper": enrichment.config.AUTO_CONFIRM_MAPPER})

    assert said, "a kind that stamps nothing answered with silence"
    assert "sweep" in said, "the refusal does not name the rule, so nobody can act on it"
    # ⚰️ [판정 505 · 507] THIS REQUIRED THE MAPPER NAME IN THE SENTENCE. The seat
    #   writes the READABLE label instead - 「decide」 rather than `declared:decide` -
    #   because 507 settled that a tag an operator cannot read is the defect, and the
    #   rule name above is what they act on. What must not happen is a refusal that
    #   says neither, so the label is asserted rather than the assertion dropped.
    from chain import dynamic_mappers

    label = dynamic_mappers.label_for(enrichment.config.AUTO_CONFIRM_MAPPER)
    assert label and label in said, (
        "the refusal names neither the mapper nor its label: %r" % said)


def test_a_kind_that_stamps_its_origin_refuses_nothing():
    """The control: a sentence that is printed for every kind says nothing about any of
    them."""
    from chain import join_into

    # ⚰️ [652 3걸음] `vjc.JOIN_MAPPER`(`declared:virtual_join`) 였다. 그 종류가 걷혀
    #    실조인 이름으로 같은 성질을 잰다 — 스탬프를 찍는 종류는 회수를 거절하지 않는다.
    assert rule_run.retraction_refusal(
        {"name": "j", "mapper": join_into.JOIN_INTO_MAPPER}) is None
    assert rule_run.retraction_refusal(
        {"name": "j2", "mapper": join_into.JOIN_INTO_MAPPER}) is None


STAMPED = {"origin_row_id": "src-1", "updates": {"part_no": "P-1"}}
UNSTAMPED = {"updates": {"part_no": "P-1"}}


# 총괄 4c3417ccb ③ — what the rule's output said decides; a rule not run yet is not warned about.
@pytest.mark.parametrize("output,stamps,refuses", [
    ([], None, False),                       # ran and proposed nothing: still not known
    ([STAMPED], True, False),
    ([UNSTAMPED], False, True),
    ([UNSTAMPED, STAMPED], True, False),
])
def test_a_mappers_refusal_is_what_its_output_said(monkeypatch, output, stamps, refuses):
    import mapper_sdk

    monkeypatch.setattr(rule_run, "_ORIGIN_SEEN", {})
    name = "s280_probe_mapper"
    mapper_sdk.register(name, lambda db, payload, rule=None: {"updates": [dict(i) for i in output]})
    rule = {"name": "custom", "mapper": name, "target_table": TARGET}
    try:
        assert rule_run.retraction_refusal(rule) is None, "a rule that has not run was warned about"
        answer = rule_run.run_rule(None, rule, payloads=[{"row_id": "src-1"}])
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop(name, None)
        mapper_sdk.MAPPER_PARAMS.pop(name, None)

    assert answer["stamps_origin"] is stamps
    said = rule_run.retraction_refusal(rule)
    assert (said is not None) is refuses, said
    assert not refuses or "custom" in said


def test_every_registered_kind_answers_the_question_one_way_or_the_other():
    """🔴 THE CENSUS, AS A GATE. 판정 432 asked for the population to be counted before
    anything was built; this keeps it counted. A kind registered later with no answer here
    would otherwise retract nothing and say nothing - today's picture, arriving again under
    a new name."""
    # ⚰️ [판정 562] THE POPULATION MOVED WITH THE TABLE. It was the `builtin:` kinds;
    #   it is the mappers the product builds from declarations, and the fact it asks about
    #   travelled with them into `TEMPLATE_FACTS`.
    from chain import dynamic_mappers

    assert dynamic_mappers.TEMPLATE_FACTS, "nothing is registered, so this asserts nothing"
    for kind in sorted(dynamic_mappers.TEMPLATE_FACTS):
        answer = rule_run.retraction_refusal({"name": "r", "mapper": kind})
        stamps = dynamic_mappers.stamps_origin(kind)
        assert (answer is None) is stamps, (
            "kind %r is %sregistered as stamping its origin but the seat says %r"
            % (kind, "" if stamps else "not ", answer))


def _claimed(db, table, source, columns):
    """The product's claim predicate read back as cells: [(row_id, column, line)] the source still says."""
    from sqlalchemy import select

    from chain import cell_layer

    lt, bits = cell_layer.claimed_lines(db, table)
    return [(line["row_id"], col, line) for line in db.execute(
        select(lt).where(*cell_layer._claimed_filter(lt, bits, source, columns))).mappings()
        for col in cell_layer._claimed_cells(line, bits, columns)]
