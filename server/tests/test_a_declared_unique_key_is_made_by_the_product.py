# -*- coding: utf-8 -*-
"""S-240. 통합 join 의 `key.unique` 를 «제품이» 성립시킨다 — 그 칸을 아무도 안 읽고 있었다.

🔴 THE CELL WAS WRITTEN AND READ BY NOBODY. `rule_shape` carried `on`, `derive`, `into` and
`limits` and dropped `key` on the floor, and the only place that builds a `uq_vjoin_*` is the
OLD read-time shell. So the plan's 「선언이 key.unique 라고 말하면 제품이 성립시킨다」 and
RUN.md's 「제품이 인덱스를 세웁니다」 were both FALSE for a unified join - a sentence about a
cell that could not reach anything.

⚠️ THE SHELL CALLS IT, NOT `join_into`. That module must not import `virtual_join` - its own
test asserts that boundary - so it answers 「what would an index on my right key have to
cover」 and the shell, which knows both halves, does the building.

⛔ LOAD TIME, NEVER THE READ PATH (§0-ter ①), and `enabled: false` means ZERO calls (판정 399
③′): a switch that still probes is the defect that took the read path down on 2026-09-14.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import join_into, rule_shape, synthesis# noqa: E402
from chain import unique_key                                  # noqa: E402

DECLARATION = {
    "name": "s240_join", "enabled": True,
    "on": {"table": "s240_right"}, "into": {"table": "s240_left"},
    "key": {"unique": True},
    "derive": {"kind": "join",
               "join": {"on": [{"left": "job", "right": "job"}],
                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
}


def _rule(**over):
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION))
    rule.update(over)
    return rule


@pytest.fixture(name="calls")
def fixture_calls(monkeypatch):
    seen = []
    monkeypatch.setattr(unique_key, "ensure_once",
                        lambda db, name, table, columns, folds=None:
                        seen.append((name, table, list(columns), list(folds or ())))
                        or {"state": "ok", "created": None})
    return seen


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the cell survives at all
# ---------------------------------------------------------------------------

def test_the_key_cell_survives_the_translation_and_the_round_trip():
    """⚰️ IT DID NOT. `from_declaration` built a fixed dict with no room for `key`, so the
    operator could write the cell, the form could draw it, and nothing downstream would ever
    see it - 「폼이 그리는데 읽는 쪽이 없다」 one more time."""
    internal = rule_shape.from_declaration(DECLARATION)

    assert internal["key"] == {"unique": True}
    assert rule_shape.to_declaration(internal)["key"] == {"unique": True}
    assert rule_shape.as_chain_rule(internal)["key"] == {"unique": True}


def test_the_cell_is_not_a_mapper_argument():
    """⚠️ IT SITS BESIDE `params`, NOT INSIDE IT. `join_into` never reads it - the index is
    the shell's business - and putting it in `params` would tell the next reader otherwise."""
    rule = _rule()

    assert "key" not in (rule.get("params") or {})
    assert "unique" not in join_into.join_spec(rule)


def test_join_into_says_what_an_index_would_cover_without_knowing_what_an_index_is():
    """🔴 THE FOLD COMES FROM THE ONE PLACE THAT COMPUTES IT. The index and the join must be
    built from the SAME expression or PostgreSQL silently stops using the index (S-181), so
    the module that folds the join key is the module that answers this."""
    import inspect

    table, columns, folds = join_into.right_key(_rule())

    assert (table, columns) == ("s240_right", ["job"])
    assert len(folds) == len(columns)
    assert folds == [None], "neither side of this pair declares a notation"
    imports = [line.strip() for line in inspect.getsource(join_into).splitlines()
               if line.strip().startswith(("import ", "from "))]
    assert not [line for line in imports if "virtual_join" in line], (
        "the boundary S-237 asserted was crossed to build an index")


def test_a_folded_join_key_requires_a_DIFFERENT_index_and_says_so(monkeypatch):
    """🔴 [S-181] A FOLDED KEY IS UNIQUENESS OVER THE FOLDED EXPRESSION, NOT THE COLUMN. If
    the fold is dropped on the way to the index, the product asks for `uq_…_ns` while the
    join compares `lower(replace(...))` - PostgreSQL builds it, uses it for nothing, and the
    duplicate the index was supposed to refuse walks in.

    ⚠️ AND THE FIXTURE HAD TO DECLARE A NOTATION TO SAY THIS AT ALL. With neither side
    declared the fold is `None`, so a `right_key` that returned `None` for every column was
    indistinguishable from one that computed it - the legend was feeding the assertion."""
    import notation_norm
    from chain import join_key_index as vjc

    monkeypatch.setattr(notation_norm, "normalized_by_table",
                        lambda: {"s240_right": {"job": {"rules": {"separator": True,
                                                                  "case": True}}}})
    table, columns, folds = join_into.right_key(_rule())

    assert folds != [None], "the declaration this fixture makes must reach the index"
    assert "_nf" in vjc.required_index_name(table, columns, folds)
    assert "_nf" not in vjc.required_index_name(table, columns, [None])


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the shell builds it, and only when asked
# ---------------------------------------------------------------------------

def test_a_declared_unique_key_is_ensured_on_the_right_table(calls):
    report = synthesis.ensure_declared_unique_keys(None, [_rule()])

    # ⚠️ ONE FOLD PER COLUMN, `None` WHERE NEITHER SIDE DECLARES A NOTATION. The list is
    # positional - a short list would silently fold the wrong column - which is why
    # `right_key` returns one entry per column rather than only the folds that exist.
    assert calls == [("s240_join", "s240_right", ["job"], [None])]
    assert [name for name, _r in report["ensured"]] == ["s240_join"]


def test_a_disabled_declaration_touches_the_database_zero_times(calls):
    """⛔ 판정 399 ③′. A switch that still probes is not a switch - and the skip says WHICH
    rule and why, because a skip nobody can see is the silence every refusal exists to break."""
    report = synthesis.ensure_declared_unique_keys(None, [_rule(enabled=False)])

    assert calls == []
    assert report["skipped"] == [("s240_join", "enabled=false")]


def test_a_declaration_that_says_nothing_about_uniqueness_gets_no_index(calls):
    """⚠️ ABSENT IS NOT 「no」 TO A QUESTION NOBODY ASKED. A join that never claimed a unique
    key gets NO INDEX - and `join_into`'s own row-level net still refuses a left row with two
    right answers (`593aac50`).

    🔴 [판정 680] 「그리고 아무 말도 안 한다」가 이 줄의 «둘째 절»이었고, 그것이 바뀌었습니다.
    걷는 이는 꺼진 조인에 «사유»를 내면서 유일성을 안 적은 조인에는 아무것도 안 냈습니다 —
    한 축에서 한 비답은 말하고 다른 비답은 조용했던 것입니다. 이제 둘 다 말합니다.

    ⚠️ 그래서 «워밍업 로그에 줄이 하나 생깁니다»(`[Warmup] 유일 키 설치 건너뜀`). 그것이
    이 변경의 값이자 비용이고, 여기서 단언하는 이유는 그 줄이 «조용히» 생기거나 «조용히»
    사라지지 않게 하기 위해서입니다. 인덱스는 그대로 «0» 입니다 — 말이 늘었지 일이 는 게
    아닙니다.
    """
    rule = _rule()
    rule.pop("key")

    report = synthesis.ensure_declared_unique_keys(None, [rule])

    assert calls == [], "승인을 안 물은 선언에 DDL 이 돌았습니다"
    assert report["ensured"] == []
    assert [name for name, _why in report["skipped"]] == ["s240_join"]
    assert "key.unique" in report["skipped"][0][1]


def test_a_rule_that_is_not_this_kind_is_not_this_seats_business(calls):
    """⚠️ THE LEGACY DECLARATION'S JOIN KEEPS ITS OWN SEAT. Two places building one table's
    index would be two answers to 「does this exist」. (It was called 「the old read-time
    join」 here; it is not one - ruling 461 retired that half and `builtin:join` is the
    OTHER WRITE DOOR, 판정 461 ③.)

    🔴 THE FIXTURE DIFFERS FROM THE TARGET BY THE MAPPER NAME AND NOTHING ELSE. My first
    cut handed this seat rules with no `params` at all, so dropping the kind check changed
    nothing - they fell out one line later for having no right key, and a fixture that
    cannot hold the defect scores 「no problem」 rather than 「no defect」."""
    from chain import join_key_index as vjc

    synthesis.ensure_declared_unique_keys(None, [
        _rule(mapper="declared:some_other_kind", name="old_one"),
        _rule(mapper=None, mapper_module="m", mapper_function="f", name="file_one")])

    assert calls == []


def test_the_columns_cell_is_read_and_agreeing_with_the_join_changes_nothing(calls):
    """⚠️ `key.columns` IS A CHECK, NOT A CHOICE. The index must be built over the join's own
    right key or PostgreSQL will not use it (S-181), so the list cannot pick other columns -
    but it is READ, because a cell nobody looks at is the defect this whole round is about."""
    rule = _rule()
    rule["key"] = {"unique": True, "columns": ["job"]}

    synthesis.ensure_declared_unique_keys(None, [rule])

    assert calls == [("s240_join", "s240_right", ["job"], [None])]


def test_columns_that_are_not_the_joins_right_key_are_refused_by_name(calls):
    """🔴 HONOURING IT SILENTLY WOULD BUILD AN INDEX THAT COVERS NOTHING THIS JOIN COMPARES.
    The operator gets a sentence naming both lists and fixes one word; `join_into`'s own
    row-level net still refuses a left row with two right answers meanwhile."""
    rule = _rule()
    rule["key"] = {"unique": True, "columns": ["lot"]}

    report = synthesis.ensure_declared_unique_keys(None, [rule])

    assert calls == []
    assert len(report["skipped"]) == 1
    name, why = report["skipped"][0]
    assert name == "s240_join" and "['lot']" in why and "['job']" in why


def test_a_join_with_no_right_key_is_skipped_by_name(calls):
    rule = _rule()
    rule["params"] = dict(rule["params"], on=[])

    report = synthesis.ensure_declared_unique_keys(None, [rule])

    assert calls == []
    assert report["skipped"] == [("s240_join", "no right key to cover")]


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the seat is load time, and it cannot stop the worker
# ---------------------------------------------------------------------------

def test_the_seat_is_the_index_work_which_has_both_the_rules_and_a_session():
    """🔴 `load_chain_rules()` HAS NO SESSION and the read path is where §0-ter ① forbids new
    SQL, so the seat is the one place where 「the rules were just read」 meets 「there is a
    database」 - and it runs after every reload, which is when a declaration can change.
    ⑤ (총괄 3ef5fe54f): that place left the warmup - it runs beside the loop, after its first
    beat - and the warmup no longer builds anything."""
    import inspect

    from chain import ingestion_worker as worker

    body = inspect.getsource(worker._ensure_declared_indexes_sync)

    assert "ensure_declared_unique_keys" in body and "retract_unrequired_indexes_once" in body
    assert "ensure_declared_unique_keys" not in inspect.getsource(worker_warmup())


def test_a_failure_to_build_an_index_does_not_stop_the_worker(monkeypatch, caplog):
    """⛔ CONTAINED. An index that cannot be built is a named line, never a worker that will
    not start - the join still refuses a fanned-out left row by itself."""
    import logging

    from chain import ingestion_worker as worker

    monkeypatch.setattr(unique_key, "ensure_once",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no pg_index")))

    with caplog.at_level(logging.ERROR):
        worker._ensure_declared_indexes_sync([_rule()], lambda: _FakeSession())

    assert "no pg_index" in " ".join(r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# 🔴 ⓓ — S-248: the index is kept by the very retraction that enforces its lifetime
# ---------------------------------------------------------------------------

def test_one_declaration_stands_two_rules_and_asks_for_one_index(calls):
    """⚠️ THE DECLARATION'S RULE AND ITS `:target` COMPANION JOIN THE SAME TWO TABLES. Asking
    twice would probe `pg_index` twice at every reload and report one index as two."""
    from chain import rule_shape

    stood, refusal, _notes = rule_shape.expand_declaration(DECLARATION, {})

    assert refusal is None and len(stood) == 2
    report = synthesis.ensure_declared_unique_keys(None, stood)
    assert len(calls) == 1 and len(report["ensured"]) == 1


def test_the_name_this_seat_requires_is_the_name_the_builder_would_build():
    """🔴 A DRIFT HERE IS SILENT AND PERMANENT. If the name we call 「required」 differs by
    one character from the name `ensure` creates, the product builds an index at warmup and
    retracts it on the next read, forever - so the required name is asked of the same
    function that NAMES the index, off the same three values `ensure` is handed."""
    from chain import join_key_index as vjc

    table, columns, folds = join_into.right_key(_rule())

    assert vjc.required_index_name(table, columns, folds) in vjc.required_index_ddl(
        table, columns, **({"folds": folds} if folds and any(folds) else {}))


def test_the_required_set_the_retraction_is_handed_names_the_unified_joins_index(monkeypatch):
    """🔴 S-248 MEETS S-240. An index lives exactly as long as the join that requires it -
    and after this round there are TWO kinds of join that require one, both wearing the
    `uq_vjoin_` prefix. The retraction could only see the read-time declarations, so the
    index built here would be dropped by the next load: built at warmup, retracted on the
    next read, built again at the next restart.

    🔴 [판정 652] THE SEAT MOVED AND THE PROMISE DID NOT. The retraction used to run inside
    the read-time join loader, which is retiring; it now runs in `chain.synthesis`, beside
    the seat that BUILDS the index. If the move had lost this, the real join's index would
    have had nobody to take it back - S-248 on the half that stays."""
    from chain import ingestion_worker, join_key_index, synthesis

    seen = {}
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"rules": [DECLARATION], "document": {},
                                           "path": "x", "exists": True, "error": None})
    monkeypatch.setattr(unique_key, "retract_unrequired_once",
                        lambda db, required: seen.setdefault("required", set(required)))

    synthesis.retract_unrequired_indexes_once(None, known_tables={})

    assert join_key_index.required_index_name("s240_right", ["job"], [None]) in seen["required"]


# ⚰️ [판정 652 3걸음] `test_the_required_set_holds_both_producers_while_both_grammars_live`
#    가 여기 있었습니다 — Q-192 의 게이트입니다. 회수의 «요구 집합»이 한쪽 문법만 들면 다른
#    쪽의 살아 있는 인덱스를 걷는다(S-248 의 장애)를 쟀고, 이름이 그 수명을 «스스로» 적어
#    뒀습니다: 「while both grammars live」. 하나가 됐으므로 요구 집합에 반쪽이 없습니다.
#    🔴 남는 교훈은 시험이 아니라 «기억»에 있습니다 — 좌석을 옮길 때 호출은 따라가고 입력의
#    반쪽은 남는다.


def test_a_required_set_that_cannot_see_both_producers_retracts_nothing(monkeypatch):
    """⛔ HALF A REQUIRED SET DOES NOT RETRACT A LITTLE LESS - IT RETRACTS THE WRONG THING.

    🔴 [판정 652] AND THIS IS NOW STRUCTURAL RATHER THAN A RULE THE SEAT FOLLOWS. The old
    seat could be HANDED a partial list and had to refuse; the new one takes no list at all,
    so the only set it can compute is the complete one. What is left to assert is that a
    required set which cannot be computed produces NO retraction rather than an empty one -
    an empty required set retracts every product index there is.

    ⚠️ 이 줄은 «공허하기 쉽습니다». 이사 직후 이 시험은 「회수를 아예 안 부르니 called 가
    비었다」로 거저 초록이었습니다 - 그래서 이제 새 좌석을 «직접» 부릅니다."""
    from chain import synthesis

    called = []
    monkeypatch.setattr(synthesis, "declared_unique_index_names",
                        lambda **_k: (_ for _ in ()).throw(RuntimeError("no catalogue")))
    monkeypatch.setattr(unique_key, "retract_unrequired_once",
                        lambda db, required: called.append(required))

    with pytest.raises(RuntimeError):
        synthesis.retract_unrequired_indexes_once(None, known_tables={})

    assert called == [], "요구 집합을 못 구했는데 «빈 집합»으로 회수하면 전부 걷힙니다"


def test_a_declaration_that_is_switched_off_requires_no_index(monkeypatch):
    """⚠️ AND THAT IS THE RETRACTION DOING ITS JOB, not a hole. A join nobody runs cannot be
    the reason a write is refused with 23505 - which is the outage S-248 closes."""
    from chain import join_key_index as vjc
    from chain import ingestion_worker

    off = dict(DECLARATION, enabled=False)
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"rules": [off], "document": {}, "path": "x",
                                           "exists": True, "error": None})

    assert synthesis.declared_unique_index_names(known_tables={}) == set()


class _FakeSession:
    def close(self):
        pass


def worker_warmup():
    from chain import ingestion_worker

    return ingestion_worker.warmup_worker
