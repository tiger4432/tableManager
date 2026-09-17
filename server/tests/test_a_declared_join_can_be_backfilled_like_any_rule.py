# -*- coding: utf-8 -*-
"""S-242 (판정 403). 소급이 `builtin:` 종류를 «돌릴 수 있다» — 라이브와 소급이 한 문.

🔴 THE OWNER ASKED 「이거 켜려면 어케해 소급」 AND THERE WAS NO ANSWER. `replay_rule` knew only
`mapper_module`/`mapper_function`, which a `builtin:` rule leaves empty - so
`importlib.import_module(None)` threw and a migrated join had NO backfill at all. The worker
ran the same rule through `builtins.run_builtin` (⚰️ 판정 498: both doors are now one seat,
`chain.rule_run.run_rule`). Live and retroactive were two doors to one
rule, which is the 「같은 기능에 두 경로」 defect at its most expensive: one door simply did
not open.

⛔ ISOLATION IS ON THE BUILTIN BRANCH ONLY (판정 403). Measured before building: the page loop
has NO try around the mapper call, so one bad page kills the whole run. That is worth fixing
and it is not this round's subject - the file mapper's call is byte for byte what it was, and
whether IT should isolate is queued as S-242-b.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import builtins, join_into, replay, rule_shape            # noqa: E402
from database.database import Base                                   # noqa: E402
from database import crud, models, schemas                           # noqa: E402

LEFT = "s242_left"
RIGHT = "s242_right"

TABLES = {
    LEFT: {"business_key": "log_key",
           "column_types": {"log_key": "string", "job": "string",
                            "lot_confirmed": "string"}},
    RIGHT: {"business_key": "job",
            "column_types": {"job": "string", "lot": "string"}},
}

DECLARATION = {
    "name": "s242_join", "enabled": True,
    "on": {"table": LEFT}, "into": {"table": LEFT},
    "derive": {"kind": "join",
               "join": {"right_table": RIGHT,
                        "on": [{"left": "job", "right": "job"}],
                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.create_missing_dynamic_tables(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _rules():
    internal = rule_shape.from_declaration(DECLARATION)
    return [rule_shape.as_chain_rule(internal)] + rule_shape.companion_rules(internal)


def _seed(db):
    crud.apply_batch_updates(db, RIGHT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"job": "J1", "lot": "LOT-1"},
                                  source_name="seed", updated_by="s242")], silent=True))
    crud.apply_batch_updates(db, LEFT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"log_key": "L%d" % n, "job": "J1"},
                                  source_name="seed", updated_by="s242")
        for n in (1, 2)], silent=True))
    db.commit()


def _left(db):
    return {r.log_key: r.lot_confirmed
            for r in db.query(models.DYNAMIC_TABLES[LEFT]).all()}


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the door opens (gate ⑤ of the order)
# ---------------------------------------------------------------------------

def test_a_replay_of_a_declared_join_fills_the_rows_that_were_already_there(db):
    """🔴 THE BACKFILL THE OWNER ASKED FOR. Two left rows that existed before the join was
    declared, one right row - and after the replay both carry the answer."""
    _seed(db)

    stats = replay.replay_rule(db, _rules()[0], apply=True, log=lambda m: None)

    assert _left(db) == {"L1": "LOT-1", "L2": "LOT-1"}
    assert stats["rows_written"] == 2
    assert stats["self_writing_kind"] == join_into.JOIN_INTO_MAPPER


def test_a_backfill_page_makes_ONE_event_not_one_per_row(db):
    """🔴 [S-279, 판정 421] THE LAST DOOR THAT DID NOT COLLAPSE. Measured before wiring:
    `replay.py` called `outbox_mode` ZERO times, while the group path and the follow-up lap
    both collapse. So the SAME rule writing the SAME rows produced one event live and N events
    retroactively, and whatever watched the target table saw a different shape depending on
    which door the write came in through - 「같은 기능에 두 경로」 in the quiet form that raises
    nothing. A backfill is the largest batch this product runs, so it was also the worst place
    for it.

    ⛔ FIVE ROWS, BECAUSE ONE CANNOT TELL THE TWO APART. With a single row 「collapsed」 and
    「one per row」 produce the same count, and a fixture both rules agree on decides nothing.
    """
    crud.apply_batch_updates(db, RIGHT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"job": "J5", "lot": "LOT-5"},
                                  source_name="seed", updated_by="s279")], silent=True))
    crud.apply_batch_updates(db, LEFT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"log_key": "M%d" % n, "job": "J5"},
                                  source_name="seed", updated_by="s279")
        for n in range(5)], silent=True))
    db.commit()
    before = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).count()

    stats = replay.replay_rule(db, _rules()[0], apply=True, log=lambda m: None)

    assert stats["rows_written"] == 5, "the backfill did not write, so this proves nothing"
    made = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == LEFT).count() - before
    assert made == 1, (
        "the backfill wrote 5 rows and produced %d outbox events - the shape S-249 removed "
        "from the follow-up lap and S-278 from the group path" % made)


def test_a_dry_run_writes_nothing_and_says_what_it_would_be_handed(db):
    """⚠️ A DRY RUN OF A SELF-WRITING KIND CANNOT SAY WHICH CELLS IT WOULD CHANGE without
    writing to find out. It says how many ROWS it would recompute, which is the honest answer
    and the one the pre-count needs."""
    _seed(db)

    stats = replay.replay_rule(db, _rules()[0], apply=False, log=lambda m: None)

    assert _left(db) == {"L1": None, "L2": None}, "a dry run wrote"
    assert stats["rows_written"] == 0
    assert stats["mapper_items"] == 2


# ---------------------------------------------------------------------------
# ⛔ ⓑ — one page is one page (§0-ter ②, and only on this branch)
# ---------------------------------------------------------------------------

def test_a_page_that_throws_costs_that_page_and_the_session_survives(db, monkeypatch):
    """🔴 SCORED ON THE SESSION, NOT ONLY ON THE COUNT. On PostgreSQL a failed statement
    aborts the transaction, so 「the run continued」 is not enough - the next page's SELECT has
    to work, which is what the rollback buys."""
    _seed(db)
    calls = {"n": 0}

    def flaky(session, rule, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("psycopg2.errors.UniqueViolation: duplicate key")
        return {"written": len(kwargs.get("row_ids") or ())}

    # ⚰️ [판정 498] THE KIND, NOT THE DOOR. `builtins.run_builtin` is deleted; the seat looks
    #    the implementation up in this table, so replacing the entry is how the page failure
    #    is staged now - and it exercises one more real step than patching the door did.
    monkeypatch.setitem(builtins.BUILTIN_KINDS, join_into.JOIN_INTO_MAPPER, flaky)
    rolled = []
    real_rollback = db.rollback
    monkeypatch.setattr(db, "rollback",
                        lambda: rolled.append(True) or real_rollback())

    stats = replay.replay_rule(db, _rules()[0], apply=True, chunk_size=1,
                               log=lambda m: None)

    assert stats["pages_failed"] == 1
    assert "UniqueViolation" in stats["page_failures"][0]["error"]
    assert stats["rows_written"] == 1, "the page after the bad one still ran"
    # 🔴 THE ROLLBACK IS SCORED DIRECTLY, AND A MUTATION IS WHY. Asserting 「SELECT 1
    # still works」 is VACUOUS on SQLite: a failed statement does not poison the session
    # there, so removing the rollback left this test green. The behaviour §0-ter ② is about
    # is PostgreSQL's aborted transaction, and what this path owes is the rollback itself.
    assert rolled == [True], "the session was not rolled back before the next page"
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_a_refusal_from_the_kind_is_counted_and_named_rather_than_thrown(db,
                                                                         monkeypatch):
    """⛔ A REFUSAL IS AN ANSWER, and it belongs in the report beside the failures rather than
    as an exception the caller has to translate."""
    _seed(db)
    monkeypatch.setitem(builtins.BUILTIN_KINDS, join_into.JOIN_INTO_MAPPER,
                        lambda *a, **k: {"written": 0, "refusal": "right table is gone"})

    stats = replay.replay_rule(db, _rules()[0], apply=True, log=lambda m: None)

    assert stats["pages_failed"] == 1
    assert stats["page_failures"][0]["error"] == "right table is gone"


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — what replay must NOT be asked to do
# ---------------------------------------------------------------------------

def test_the_reference_side_rule_is_refused_by_name():
    """⛔ REPLAYING THE FOLLOW-UP HALF IS THE SAME ANSWER, PAID FOR TWICE. It walks every
    reference row and re-finds its targets - work the target-side rule already does for every
    row. An operator who ran both would pay twice, so the name is refused with the way out."""
    rules = _rules()
    reference = rules[1]

    with pytest.raises(replay.ReplayRefused) as raised:
        replay.find_rule(reference["name"], rules)

    assert "follow-up half" in str(raised.value)
    assert "Replay that one instead" in str(raised.value)


def test_the_target_side_rule_is_found_normally():
    """🔴 THE DISCRIMINATOR, AND IT EARNED ITS KEEP. The first cut asked 「is it
    `follow_up`」 - and BOTH halves of a unified join are paced (S-237), so it refused the
    very rule an operator should replay. This went red and the guard became a PROPERTY: the
    reference side is the one triggered on the table it READS, which is not the table it
    writes. The same lesson as 판정 387→388, one round later."""
    rules = _rules()

    assert replay.find_rule(rules[0]["name"], rules)["name"] == "s242_join"
    assert replay.is_reference_side(rules[1]) is True
    assert replay.is_reference_side(rules[0]) is False
    assert rules[0].get("follow_up") == rules[1].get("follow_up") is None, (
        "the two halves differ by their trigger; S-278 took BOTH off the paced lap")


def test_a_rule_that_is_not_in_the_set_is_refused_as_before():
    """⚠️ 「not found or disabled」 IS UNCHANGED - a disabled rule never reaches the list, so
    the switch is already the one off switch (§0-ter ③)."""
    with pytest.raises(replay.ReplayRefused) as raised:
        replay.find_rule("s242_no_such_rule", _rules())

    assert "not found or disabled" in str(raised.value)


def test_the_file_mapper_call_is_unchanged():
    """⚠️ GATE ④: 「파일 맵퍼 경로는 한 글자도 안 바뀐다」. The isolation this round adds is on
    the builtin branch only - whether the file path should isolate too is a different
    question, queued as S-242-b, and answering it here would change a path this round
    promised not to touch."""
    import inspect

    body = inspect.getsource(replay.replay_rule)
    file_call = body[body.index("The REAL mapper invocation path"):]

    assert "try:" not in file_call.split("items, metadata_items")[0], (
        "the file mapper's call grew a try this round")


# ---------------------------------------------------------------------------
# 🔴 ⓓ — the pre-count must not say 「0 cells」 about a run that rewrites everything
# ---------------------------------------------------------------------------

def test_the_pre_count_reports_rows_for_a_kind_that_writes_its_own_cells(db,
                                                                         monkeypatch):
    """🔴 MEASURED, AND IT WAS WRONG. The count reads `cells_proposed`, which a builtin rule
    leaves at 0 - so the screen an operator consents on would have said 「0 셀을 다시
    씁니다」 before a backfill that rewrites every target row. A pre-count that says
    「nothing」 about a run that does everything is worse than no pre-count."""
    from admin import retroactive

    _seed(db)
    monkeypatch.setattr(replay, "find_rule",
                        lambda name, rules=None, row_scoped=False: _rules()[0])

    answer = retroactive._count_chain_replay(db, {"rule": "s242_join"}, 1000)

    assert answer["affected"] == 2
    assert answer["affected_label"] == "다시 계산할 행"
    assert "2행을 다시 계산합니다" in answer["detail"]
