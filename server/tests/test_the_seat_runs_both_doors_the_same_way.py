# -*- coding: utf-8 -*-
"""S-279 · 판정 420 ㉡. `run_rule` RUNS both kinds and answers about them in one shape.

🔴 THIS IS THE 「돈다」 HALF. Its sibling `test_a_rule_is_run_by_one_seat.py` reads the AST and
can only say 「nobody else calls a door」 - true of a seat that has never run. Here the real
`builtin:join` writes into a real table through the real `run_builtin`, and a real file mapper
is imported and called through the real `execute_custom_mapper`, and the two answers are
compared CELL BY CELL. 소유자 2026-09-16: 「맵퍼 한 문인데 왜 이름이 달라」.

⚠️ THE MAPPER IS A FIXTURE, THE DOOR IS NOT. Live mappers are the operator's files and are
gitignored, so the module below is written for this test - but it is imported by
`importlib.import_module` from `sys.path` exactly as an operator's file is, which is the part
that broke when a builtin reached that door as `(None, None)`.
"""
import logging
import os
import sys
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import rule_run, rule_shape                                # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

LEFT = "s279_log"
RIGHT = "s279_attribution"

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

DECLARATION = {
    "name": "s279_lot_from_attribution",
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
                                  updated_by="s279") for row in rows]))


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _join_rule():
    return rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION))


@pytest.fixture(name="file_mapper")
def fixture_file_mapper(tmp_path, monkeypatch):
    """A real module on `sys.path`, imported through the real door.

    It records every call so the fan-out (one call per row vs one call per group) can be
    counted rather than assumed, and it proposes one update per payload it was handed.
    """
    module = tmp_path / "s279_probe_mapper.py"
    module.write_text(textwrap.dedent('''
        CALLS = []

        def map_it(db, payload):
            handed = payload if isinstance(payload, list) else [payload]
            CALLS.append(len(handed))
            return {"updates": [{"business_key_val": p.get("log_key"),
                                 "updates": {"note": "seen"}} for p in handed]}
    '''), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("s279_probe_mapper", None)
    import importlib

    loaded = importlib.import_module("s279_probe_mapper")
    yield loaded
    sys.modules.pop("s279_probe_mapper", None)


def _mapper_rule(**over):
    rule = {"name": "s279_note_from_payload", "trigger_table": LEFT, "target_table": LEFT,
            "mapper_module": "s279_probe_mapper", "mapper_function": "map_it"}
    rule.update(over)
    return rule


def _said(caplog):
    return [r.getMessage() for r in caplog.records
            if ("[%s]" % rule_run.RULE_LOG_TAG) in r.getMessage()]


def _cells(line):
    """The NAMES on a line, in order. Two kinds saying the same thing must say it with the
    same words - that is the half of 「문 가르기」 that lives in the log."""
    return [piece.split("=", 1)[0] for piece in line.split() if "=" in piece]


# ---------------------------------------------------------------------------
# the builtin door - a kind that writes for itself
# ---------------------------------------------------------------------------

def test_the_seat_runs_a_builtin_and_the_value_arrives(db, caplog):
    _push(db, RIGHT, [{"job": "J-1", "lot": "LOT-1"}])
    _push(db, LEFT, [{"log_key": "L-1", "job": "J-1"}])
    db.commit()
    handed = [r.row_id for r in _rows(db, LEFT)]

    caplog.clear()
    with caplog.at_level(logging.INFO):
        answer = rule_run.run_rule(db, _join_rule(), row_ids=handed)

    assert [r.lot_confirmed for r in _rows(db, LEFT)] == ["LOT-1"], (
        "the seat did not actually run the join")
    assert answer["written"] == 1
    assert answer["refusal"] is None
    # 🔴 A KIND THAT WRITES FOR ITSELF PROPOSES NOTHING, and the cells are still THERE - that
    # is what lets a caller extend all three lists without asking which door ran.
    assert answer["updates"] == []
    assert answer["map_metadata_updates"] == []
    assert answer["batches"] == []
    assert _said(caplog), "the seat said nothing about a rule that ran"


def test_the_seats_builtin_write_makes_ONE_event_not_one_per_row(db):
    """🔴 FIVE ROWS, BECAUSE ONE CANNOT TELL THE TWO APART (S-278 A-bis, re-measured here).
    With a single row 「collapsed」 and 「one per row」 produce the same count. The collapse used
    to be something each caller had to remember - the follow-up lap wrapped it, the group path
    learned to, replay never did - and it lives in the seat now."""
    _push(db, RIGHT, [{"job": "J-5", "lot": "LOT-5"}])
    _push(db, LEFT, [{"log_key": "L-%d" % n, "job": "J-5"} for n in range(5)])
    db.commit()
    handed = [r.row_id for r in _rows(db, LEFT)]
    before = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).count()

    answer = rule_run.run_rule(db, _join_rule(), row_ids=handed)

    assert [r.lot_confirmed for r in _rows(db, LEFT)] == ["LOT-5"] * 5
    assert answer["written"] == 5
    made = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).count() - before
    assert made == 1, (
        "the seat wrote 5 rows and produced %d outbox events - one per row is the shape "
        "S-249 removed from the follow-up lap" % made)


def test_every_registered_builtin_accepts_the_vocabulary_the_seat_passes():
    """🔴 [판정 428] ONE SIGNATURE, WHOEVER THE KIND IS. Measured 2026-09-16: of the three
    registered kinds, `builtin:join` declared neither `done` nor `**kwargs`, while the
    follow-up lap passes `done=` to every kind it dispatches. So the CAPABILITY is broken -
    that call raises `TypeError`, and because that lap's `for` sits inside its `try`, one
    raising rule would end the whole batch and the auto-confirm rules behind it would not run.
    The mismatch dates to 92257825 (2026-09-12 15:20), fifty minutes after `builtin:join`
    joined the table.

    ⚠️ 「IT HAS BEEN RAISING FOR FOUR DAYS」 IS A SENTENCE I CANNOT WRITE, and I wrote it in the
    channel before the lead corrected it (Q-12). The EVENT needs a declaration that puts that
    kind on the lap; declarations live in `server/config/*.json`, which is gitignored, and
    production cannot be measured. 「이 길로 가면 터진다」 is structure and is true; 「터지고
    있었다」 is an event and is uncounted. The reverse of 「기제가 있다 ≠ 돈다」.

    ⛔ THE FIX THAT WAS REFUSED, recorded so nobody re-derives it: 「pass `done` only to the
    kinds that take it」 makes the CALLER ask which kind it is, which is precisely what 판정 420
    removed from every other site. A kind that does not use a cell receives it and ignores it.

    ⚠️ READ OFF THE REGISTRY, NOT A LIST. A list would be true of the kinds I thought of, and
    the defect this stands in front of arrives with the NEXT kind somebody registers.
    """
    import inspect

    from chain import dynamic_mappers

    assert dynamic_mappers.TEMPLATES, "nothing is registered, so this asserts nothing"

    # ⚰️ [판정 498 · 562] THE CELLS CHANGED AND THE PROPERTY DID NOT. This required every
    #   registered kind to accept `row_ids` and `done` - the cells the two doors passed. There
    #   is one calling convention, `(db, payload[, rule=])`, and it is frozen; what this
    #   refuses is a mapper the seat cannot call without knowing which one it is.
    refuses = []
    for name, fn in sorted(dynamic_mappers.TEMPLATES.items()):
        parameters = list(inspect.signature(fn).parameters.values())
        positional = [p for p in parameters
                      if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                    inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        takes_anything = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters)
        if len(positional) < 2:
            refuses.append("%s takes %d positional args, not (db, payload): %s"
                           % (name, len(positional), inspect.signature(fn)))
        named = {p.name for p in parameters}
        if "rule" not in named and not takes_anything:
            refuses.append("%s cannot be handed its rule: %s" % (name, inspect.signature(fn)))

    assert refuses == [], (
        "these mappers refuse the one convention the seat calls with, so a caller would have "
        "to know which one it was calling: %s" % refuses)


def test_the_seat_hands_the_rule_to_the_mapper(db, monkeypatch):
    """The runtime half of the above: the rule reaches the mapper, unconditionally.

    ⚰️ [소유자 정본] THIS WAS `test_the_seat_hands_the_laps_batch_to_the_kind` and it asserted
    that `done` - the paced lap's batch note - reached the kind. There is no lap and there is
    no note: what a mapper is handed is its payload and its rule, and everything it wants to
    say comes back in its RETURN value.
    """
    import mapper_sdk

    seen = []

    def probe(db_, payload, rule=None):
        seen.append((payload, (rule or {}).get("name")))
        return {"written": len(payload if isinstance(payload, list) else [payload])}

    rule = {"name": "s279_kwarg", "mapper": "declared:s279_probe", "target_table": LEFT,
            "is_batch": True}
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "declared:s279_probe", probe)

    rule_run.run_rule(db, rule, row_ids=["r-1"])

    assert seen == [([{"row_id": "r-1"}], "s279_kwarg")], (
        "the mapper was not handed its payload and its rule: %r" % (seen,))


def test_a_batch_mapper_handed_no_rows_is_told_so_and_says_why(db, caplog):
    """⚰️ [판정 506 · 소유자 정본] THIS ASSERTED `written is None` — 「nobody counted, so the
    cell is not 0」 — and no log line at all, because the retired kind table skipped the call
    when the row list was empty.

    🔴 THE JOIN DECLARES `is_batch` NOW, and the seat's rule for that is written down: 「an
    empty batch still calls, because a batch mapper is entitled to be told its group was
    empty」. So the mapper runs, counts, and reports 0 WITH a sentence saying why - which is
    more than `None` ever said. 판정 509's distinction is intact and is being honoured in the
    other direction: 0 here means 「I counted」, and it is true.
    """
    caplog.clear()
    with caplog.at_level(logging.INFO):
        answer = rule_run.run_rule(db, _join_rule(), row_ids=[])

    assert answer["written"] == 0, "the mapper was called, so the count is a count"
    assert answer["refusal"], "a zero with no reason is the silent zero 525 forbids"
    said = _said(caplog)
    assert len(said) == 1, "the run happened, so exactly one line says so: %r" % (said,)


# ---------------------------------------------------------------------------
# the mapper door - a rule that proposes and lets the caller write
# ---------------------------------------------------------------------------

def test_the_seat_runs_a_file_mapper_and_carries_its_proposals(db, file_mapper, caplog):
    _push(db, LEFT, [{"log_key": "M-1", "job": "J-M"}])
    db.commit()

    caplog.clear()
    with caplog.at_level(logging.INFO):
        answer = rule_run.run_rule(db, _mapper_rule(), payloads=[{"log_key": "M-1"}])

    assert [item["updates"] for item in answer["updates"]] == [{"note": "seen"}]
    # 🔴 None, NOT 0. A mapper wrote nothing because writing is not its job; 「안 셌다」 and
    # 「0 이었다」 are different facts and a caller must be able to tell them apart.
    assert answer["written"] is None
    assert answer["refusal"] is None
    assert _said(caplog), "the seat said nothing about a rule that ran"


def test_a_per_row_rule_is_called_once_per_row_and_a_batch_rule_once(db, file_mapper):
    """The fan-out moved into the seat, so it is counted here rather than trusted. A batch
    mapper handed five rows in five calls would see five groups of one and fold nothing."""
    handed = [{"log_key": "M-%d" % n} for n in range(3)]

    del file_mapper.CALLS[:]
    per_row = rule_run.run_rule(db, _mapper_rule(), payloads=handed)
    assert file_mapper.CALLS == [1, 1, 1]
    assert len(per_row["updates"]) == 3, "the seat dropped rows while concatenating"

    del file_mapper.CALLS[:]
    batched = rule_run.run_rule(db, _mapper_rule(is_batch=True), payloads=handed)
    assert file_mapper.CALLS == [3]
    assert len(batched["updates"]) == 3


def test_a_decorator_registered_mapper_is_named_on_the_line_not_None_dot_None(
        db, monkeypatch, caplog):
    """🔴 THE OWNER'S PATH (소유자 2026-09-07: 「내가 운영에서 @mapper 로 했다니까?」). A rule may
    name its mapper in the ONE cell and carry no module or function at all - the door resolves
    that from `mapper_sdk.MAPPER_REGISTRY` - so a line built from module and function alone
    says `None.None` about a mapper that ran perfectly well. 「이 줄이 «참»인가」."""
    import mapper_sdk

    seen = []

    def registered(db_, payload):
        seen.append(payload)
        return {"updates": []}

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "s279_registered", registered)
    rule = {"name": "s279_one_cell", "trigger_table": LEFT, "target_table": LEFT,
            "mapper": "s279_registered"}

    caplog.clear()
    with caplog.at_level(logging.INFO):
        answer = rule_run.run_rule(db, rule, payloads=[{"log_key": "R-1"}])

    assert seen == [{"log_key": "R-1"}], "the registry path did not run"
    assert answer["written"] is None
    line = _said(caplog)[-1]
    assert "kind=s279_registered" in line, line
    # ⚠️ `written=None` IS LEGITIMATE on this line - it is the cell that says nobody counted.
    #    What must not appear is a NAME assembled from cells the rule does not carry.
    assert "kind=None" not in line, (
        "the line names the mapper by cells the rule does not carry: %r" % line)


def test_an_empty_group_still_tells_a_batch_mapper_and_asks_a_per_row_one_nothing(
        db, file_mapper):
    del file_mapper.CALLS[:]
    rule_run.run_rule(db, _mapper_rule(is_batch=True), payloads=[])
    assert file_mapper.CALLS == [0], "a batch mapper is entitled to be told its group was empty"

    del file_mapper.CALLS[:]
    rule_run.run_rule(db, _mapper_rule(), payloads=[])
    assert file_mapper.CALLS == [], "there was no row to speak about"


# ---------------------------------------------------------------------------
# 🔴 the two kinds, side by side - the assertion the whole round is for
# ---------------------------------------------------------------------------

def test_both_kinds_answer_in_the_same_shape_and_are_logged_in_the_same_words(
        db, file_mapper, caplog):
    """⛔ THE DISCRIMINANT IS THE COMPARISON, NOT EITHER HALF. Each kind on its own has always
    'worked'; what was wrong is that a caller - and an operator reading the log - had to know
    WHICH before it could read the answer. So this asserts the two answers have the same keys
    and the two lines have the same cell names, in order."""
    _push(db, RIGHT, [{"job": "J-B", "lot": "LOT-B"}])
    _push(db, LEFT, [{"log_key": "L-B", "job": "J-B"}])
    db.commit()
    handed = [r.row_id for r in _rows(db, LEFT)]

    caplog.clear()
    with caplog.at_level(logging.INFO):
        from_builtin = rule_run.run_rule(db, _join_rule(), row_ids=handed)
        builtin_line = _said(caplog)[-1]
        from_mapper = rule_run.run_rule(db, _mapper_rule(), payloads=[{"log_key": "L-B"}])
        mapper_line = _said(caplog)[-1]

    assert sorted(from_builtin) == sorted(from_mapper), (
        "the two doors answer with different cells, so a caller has to ask which ran")
    assert _cells(builtin_line) == _cells(mapper_line), (
        "the two kinds are logged in different words: %r vs %r" % (builtin_line, mapper_line))
    for line in (builtin_line, mapper_line):
        assert "rule=" in line, "a count nobody can attribute to a declaration is unactionable"
