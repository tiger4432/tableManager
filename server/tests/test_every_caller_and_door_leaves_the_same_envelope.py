# -*- coding: utf-8 -*-
"""S-279 · 판정 424 ㉠. The six cells: three callers that can run a chain rule, two doors.

🔴 WHY A MATRIX AND NOT SIX SEPARATE TESTS. The defect this round removed was never in one
cell - it was that the cells DISAGREED. A builtin's own write left with no hop, a mapper's
proposals left with one, retroactive collapsed nothing and the paced lap collapsed everything,
and every one of those was locally correct and locally tested. So the subject here is the
AGREEMENT: the same four questions, asked in the same order, of every cell.

    ① did it write            - a cell that wrote nothing makes ②③④ vacuous
    ② exactly one event       - the collapse (S-249 ⓔ-1, S-278 A-bis, 판정 421)
    ③ the author              - table, row_ids, source: 「who wrote this and for what rows」
    ④ the hop                 - `chain_depth` (판정 423), the only thing the ceiling can read

⚠️ THE FIXTURE WRITES NEW ROWS ON PURPOSE (판정 424, Q-6). `crud` suppresses the column write,
the audit log AND the outbox event when the resolved value is unchanged - and 「unchanged」 is
`float(old) != float(new)` for numbers and `str(old).strip() != ...` for text, so 「1」→「1.0」 or
a whitespace-only edit looks like a change and produces nothing. `is_new` makes `has_changed`
unconditionally true, which is the one shape that cannot be vacuous.

⚠️ ONE OF THE SIX IS STRUCTURALLY EMPTY and is asserted to be, rather than invented: the paced
lap selects `follow_up AND writes_itself`, so no file mapper can ever ride it - a file mapper
proposes, and this lap has no batch writer to put a proposal through.
"""
import json
import os
import sys
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import replay, rule_run, rule_shape                        # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

LEFT = "s424_log"
RIGHT = "s424_attribution"

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
    "name": "s424_lot_from_attribution",
    "on": {"table": LEFT},
    "derive": {"kind": "join",
               "join": {"right_table": RIGHT,
                        "on": [{"left": "job", "right": "job"}],
                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
    "into": {"table": LEFT},
}

ROWS = 4          # > 1, so 「collapsed」 and 「one per row」 cannot produce the same count


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


@pytest.fixture(name="file_mapper")
def fixture_file_mapper(tmp_path, monkeypatch):
    """A real module on `sys.path`, imported by the real door."""
    (tmp_path / "s424_probe_mapper.py").write_text(textwrap.dedent('''
        def map_it(db, payload):
            handed = payload if isinstance(payload, list) else [payload]
            # 🔴 READ THE PAYLOAD THE EXPANDER ACTUALLY BUILDS, measured rather than guessed:
            #    {row_id, business_key, data: {col: {value, ...}}, source_name, ...}. And the
            #    key column rides in `updates` as well as in `business_key_val` - the chain's
            #    key gate refuses a row whose key column carries no value, and a fixture that
            #    trips it writes nothing, which makes every other assertion in its cell vacuous.
            out = []
            for p in handed:
                # ⚠️ READ FROM `data`, WHICH IS THE ONLY KEY BOTH CALLERS BUILD. Measured
                #    2026-09-16: the group path's expander hands
                #    {row_id, business_key, data, source_name, transaction_id, updated_by,
                #    timestamp} and `replay._to_payloads` hands {row_id, data} only. A probe
                #    reading `business_key` writes live and writes NOTHING on a backfill -
                #    silently - which is how this fixture first went green in five cells of six.
                key = ((p.get("data") or {}).get("log_key") or {}).get("value")
                out.append({"business_key_val": key,
                            "updates": {"log_key": key, "note": "seen"}})
            return {"updates": out}
    '''), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("s424_probe_mapper", None)
    yield
    sys.modules.pop("s424_probe_mapper", None)


def _seed(db):
    """NEW rows, because `is_new` is the only shape `has_changed` cannot suppress."""
    crud.apply_batch_updates(db, RIGHT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"job": "J", "lot": "LOT"},
                                  source_name="seed", updated_by="s424")]))
    crud.apply_batch_updates(db, LEFT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"log_key": "L%d" % n, "job": "J"},
                                  source_name="seed", updated_by="s424")
        for n in range(ROWS)]))
    db.commit()


def _events(db, table=LEFT):
    return db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == table).all()


def _join_rules():
    return rule_shape.expand_declaration(DECLARATION, crud.TABLE_CONFIG)[0]


def _mapper_rule(**over):
    rule = {"name": "s424_note_from_payload", "enabled": True, "is_batch": True,
            "trigger_table": LEFT, "target_table": LEFT,
            "mapper_module": "s424_probe_mapper", "mapper_function": "map_it"}
    rule.update(over)
    return rule


def _written(db, column):
    return [getattr(r, column) for r in db.query(models.DYNAMIC_TABLES[LEFT])
            .order_by(models.DYNAMIC_TABLES[LEFT].log_key).all()]


def _score(db, before, cell, wrote, expect_depth=1):
    """The four questions, in the order 판정 424 ㉠ set them, for one cell of the matrix."""
    # ① did it write
    assert wrote == ["LOT"] * ROWS or wrote == ["seen"] * ROWS, (
        "%s: the rule wrote %r, so the rest of this cell would be vacuous" % (cell, wrote))

    # ② exactly one event
    made = [e for e in _events(db) if e.id not in before]
    assert len(made) == 1, (
        "%s: %d rows written produced %d outbox events - one per row is the shape S-249 "
        "removed from the lap, S-278 from the group path and 판정 421 from retroactive"
        % (cell, ROWS, len(made)))

    # ③ the author
    payload = worker.get_payload_dict(made[0])
    assert made[0].table_name == LEFT, (cell, made[0].table_name)
    assert len(payload.get("row_ids") or ()) == ROWS, (
        "%s: the collapsed event names %r rows, not the %d that were written - a reader that "
        "re-expands it would miss the rest" % (cell, payload.get("row_ids"), ROWS))
    # ⚠️ NOT PINNED TO `chain_ingestion` (판정 425). `apply_batch_updates` re-sets
    #    `request_source` to the ITEM'S LAYER NAME and the envelope reads it at that moment, so
    #    this cell carries the layer, not the channel. Pinning the channel here would encode a
    #    defect as a requirement; splitting the two facts is S-280.
    assert payload.get("source_name"), (
        "%s: the event names no author at all" % cell)

    # ④ the hop
    assert event_constants.chain_depth_of(payload) == expect_depth, (
        "%s: the event carries hop %r, not %d - `max_chain_depth` reads this and nothing else"
        % (cell, event_constants.chain_depth_of(payload), expect_depth))


# ---------------------------------------------------------------------------
# the group step - both doors
# ---------------------------------------------------------------------------

def test_the_group_step_through_the_builtin_door(db):
    _seed(db)
    before = set(e.id for e in _events(db))
    worker._process_chain_transaction_group_sync(
        "tx-424-gb", _events(db), db, _join_rules())
    _score(db, before, "group/builtin", _written(db, "lot_confirmed"))


def test_the_group_step_through_the_mapper_door(db, file_mapper):
    _seed(db)
    before = set(e.id for e in _events(db))
    worker._process_chain_transaction_group_sync(
        "tx-424-gm", _events(db), db, [_mapper_rule()])
    _score(db, before, "group/mapper", _written(db, "note"))


# ---------------------------------------------------------------------------
# ⚰️ [소유자 정본, 2026-09-17] THE PACED LAP WAS A ROW OF THIS MATRIX AND IT IS GONE
#   소유자: 「체인은 … 트랜잭션 - 아웃박스 - 트리거 - 맵퍼 실행 - 페이로드 및 업서트
#   이거만 하면됨」. Two cells lived here - `lap/builtin` and the asserted-empty
#   `lap/mapper` - and both measured a second execution path. What replaces them is not a
#   third cell but the CONTROL BELOW: the lap's own names must stay absent.
# ---------------------------------------------------------------------------

def test_the_chain_has_no_second_execution_path():
    """⛔ THE RETIRED MECHANISM'S OWN SYMPTOM, KEPT AS A CONTROL GROUP.

    🔴 A matrix loses a row silently. This does not: if any of these names comes back, a
    rule can once again be taken by something other than its trigger, and the shape 소유자
    removed - 「고장인지 느린 건지 판단 불가」, because 「안 돌았다」 and 「아직 안 돌았다」
    look the same - comes back with it.

    ⚠️ SUBJECTS MATTER HERE (판정 608): this asserts the CHAIN has one path. The ledger's
    own follow-up queue (`ledger/followup.py`) is a different subsystem and is untouched.
    """
    gone = ("_run_the_follow_up_pass", "_rules_for_the_follow_up_pass",
            "picked_up_by_the_follow_up_pass", "picked_up_by_the_group_step",
            "PICKUP_PATHS", "refuse_rules_no_path_picks_up", "rules_by_pickup_count",
            "followup_already_served", "log_followup_folded")
    back = [name for name in gone if hasattr(worker, name)]
    assert back == [], (
        "a second execution path is back: %s" % ", ".join(back))

# ---------------------------------------------------------------------------
# retroactive - both doors
# ---------------------------------------------------------------------------

def test_retroactive_through_the_builtin_door(db):
    _seed(db)
    before = set(e.id for e in _events(db))
    replay.replay_rule(db, _join_rules()[0], apply=True, log=lambda m: None)
    _score(db, before, "retroactive/builtin", _written(db, "lot_confirmed"))


def test_retroactive_through_the_mapper_door(db, file_mapper):
    _seed(db)
    before = set(e.id for e in _events(db))
    replay.replay_rule(db, _mapper_rule(), apply=True, log=lambda m: None)
    _score(db, before, "retroactive/mapper", _written(db, "note"))


# ---------------------------------------------------------------------------
# 🔴 판정 426 — the ARGUMENT, one layer below the dispatcher
# ---------------------------------------------------------------------------

def test_both_callers_hand_a_mapper_the_same_payload_keys(db, tmp_path, monkeypatch):
    """🔴 A MAPPER IS WRITTEN BY THE USER AND WAS BEING CALLED WITH TWO SHAPES. The live path
    built seven keys and retroactive built two, so a mapper reading `business_key` wrote on the
    trigger path and returned nothing on a backfill - silently, because a missing key is `None`
    and not an error. 판정 420 unified the CALL; this is the ARGUMENT.

    ⛔ THE KEY SETS ARE COMPARED, NOT CHECKED AGAINST A LIST I TYPED. A hand-written expectation
    passes the day both callers drop the same cell, which is the failure this is for.

    ⚠️ AND THE VALUES ARE NOT COMPARED, deliberately: `timestamp` differs by construction and
    `transaction_id` names the run. What must agree is the SHAPE the user's mapper reads.
    """
    (tmp_path / "s426_recording_mapper.py").write_text(textwrap.dedent('''
        SEEN = []

        def map_it(db, payload):
            for p in (payload if isinstance(payload, list) else [payload]):
                SEEN.append(sorted(p.keys()))
            return {"updates": []}
    '''), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("s426_recording_mapper", None)
    import importlib

    probe = importlib.import_module("s426_recording_mapper")
    rule = _mapper_rule(name="s426_shape", mapper_module="s426_recording_mapper")

    _seed(db)
    worker._process_chain_transaction_group_sync("tx-426", _events(db), db, [rule])
    from_group = list(probe.SEEN)

    del probe.SEEN[:]
    replay.replay_rule(db, rule, apply=True, log=lambda m: None)
    from_retroactive = list(probe.SEEN)
    sys.modules.pop("s426_recording_mapper", None)

    assert from_group and from_retroactive, (
        "one of the two doors handed the mapper nothing, so this compares nothing")
    assert from_group[0] == from_retroactive[0], (
        "the same mapper is handed different keys depending on which caller ran it:\n"
        "  group       %s\n  retroactive %s" % (from_group[0], from_retroactive[0]))


def test_the_table_question_has_one_author_and_obeys_the_switch():
    """⚠️ MOVED HERE when `test_every_declared_rule_is_picked_up_by_exactly_one_path` went
    with the roll call (소유자 정본). Two of that file's assertions measure something that
    SURVIVES the lap, so they travel rather than die with their neighbours.

    🔴 `watches_table` IS THE ONE AUTHOR of 「does this rule watch that table」, and it carries
    `enabled` WITH the table. Measured 2026-09-17: the retired paced pass asked the table and
    NOT the switch, so a rule an operator had turned off went on running there once per
    batch - 「DB 를 여전히 만지는 스위치는 반쪽 스위치다」 in its scheduling form. One author is
    what makes that impossible to reintroduce in a second spelling.
    """
    watched = {"name": "w", "trigger_table": "t", "mapper": "m"}
    assert worker.watches_table(watched, "t") is True
    assert worker.watches_table(watched, "other") is False
    assert worker.watches_table(None, "t") is False
    assert worker.watches_table({}, "t") is False
    assert worker.watches_table(dict(watched, enabled=False), "t") is False, (
        "a rule declaring enabled: false is still watched by this path")
