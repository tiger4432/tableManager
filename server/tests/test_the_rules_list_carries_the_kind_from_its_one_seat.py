# -*- coding: utf-8 -*-
"""총괄 7085e2dc6 · 3b1a7a550 — 규칙 목록이 줄마다 «종류»를 싣고, 그 종류 순으로 선다.

> 소유자: 「enrichment 탭은 이제 필요가 없어 보이는데, 체인 탭에서 그냥 리스트를 항목별로 정렬만」
>        「항목 = 종류 맞고, ㄱ으로」

🔴 THE KIND HAS ONE SEAT — `rule_shape.declared_kind`. The route stamps it on every row and orders
   by `rule_shape.DECLARED_KINDS`; the screen draws the word and keeps the order. A list of the kind
   words on the client would be a second place that asks the kind.

🔴 AND THE SEAT WAS WIDENED, NOT FLANKED. The route lists a declaration that did not stand as its
   RAW text, which runs nothing, so the registration fell back to 「mapper」 — a refused join drawn
   as a mapper, measured on the box (`aaa`, derive keys ['join'] -> 「mapper」). A raw declaration
   carries `derive` and the grammar's own reading answers; one it cannot read is 「unknown」.
   A LOADED rule carries no `derive` (15 of 15 on the box), so its answer does not move.
"""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_shape                                        # noqa: E402
from database import crud                                           # noqa: E402

SRC, DST = "k7085_src", "k7085_derived"

#: stands -> two halves, both 「decide」
DECIDE = {"name": "k7085_decide", "on": {"table": SRC}, "into": {"table": DST},
          "derive": {"kind": "decide", "decide": {"key": ["job"], "fields": ["grade"]}}}
#: a join with no `on.table` is refused by name (JOIN_NEEDS_SOURCE) and listed as its raw text
REFUSED_JOIN = {"name": "k7085_refused_join", "into": {"table": DST},
                "derive": {"join": {"on": {"job": "job"}}}}
#: a derive the grammar cannot read — the expander passes it through still carrying it
#: ⚠️ NOT `{"kind": "banana"}`: measured, that one STANDS as an empty rule that has lost its `derive`
#:    (no refusal, no mapper), so no seat can see what it said. That is the expander's gap, reported
#:    to the lead — not pinned here.
NONSENSE = {"name": "k7085_nonsense", "on": {"table": SRC}, "into": {"table": DST},
            "derive": "not a mapping"}
#: a flat rule — a mapper, today and after
FLAT = {"name": "k7085_flat", "trigger_table": SRC, "target_table": DST,
        "mapper_module": "x", "mapper_function": "y"}

TABLES = {
    SRC: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string"}, "display_columns": ["job"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "grade": "string"},
          "display_columns": ["job", "grade"]},
}


@pytest.fixture(name="declared")
def fixture_declared(tmp_path, monkeypatch):
    """⚠️ 이 박스의 라이브 설정으로 재지 않는다 — 픽스처가 문서를 «짓는다»."""
    chain_file = tmp_path / "chain_rules.json"
    chain_file.write_text(json.dumps({"rules": [FLAT, NONSENSE, REFUSED_JOIN, DECIDE]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))
    crud.TABLE_CONFIG.update(TABLES)
    import paths
    real_config_path = paths.config_path
    monkeypatch.setattr(paths, "config_path",
                        lambda name: (str(chain_file) if name == "chain_rules.json"
                                      else real_config_path(name)))
    try:
        yield
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _rows():
    import main

    answer = main.get_chain_rules()
    assert answer["status"] == "success", answer
    return answer["data"]


def test_a_refused_join_is_a_join_not_a_mapper(declared):
    """🔴 이 줄이 좌석을 넓힌 이유입니다. 원문 갈래를 지우면 여기가 「mapper」 로 빨개집니다."""
    kinds = {row["name"]: row["kind"] for row in _rows()}
    assert kinds["k7085_refused_join"] == "join"


def test_a_derive_the_grammar_cannot_read_is_unknown_never_a_guessed_word(declared):
    kinds = {row["name"]: row["kind"] for row in _rows()}
    assert kinds["k7085_nonsense"] == rule_shape.UNKNOWN_KIND


def test_a_standing_rule_answers_as_it_did_and_a_flat_rule_stays_a_mapper(declared):
    """⚠️ 음성 대조 — 넓힌 갈래가 «로드된» 규칙의 답을 옮기면 이 줄이 빨개집니다."""
    kinds = {row["name"]: row["kind"] for row in _rows()}
    assert kinds["enrichment_dedup:k7085_decide"] == "decide"
    assert kinds["enrichment_auto_confirm:k7085_decide"] == "decide"
    assert kinds["k7085_flat"] == "mapper"


def test_every_row_carries_one_of_the_seats_words(declared):
    allowed = set(rule_shape.DECLARED_KINDS) | {rule_shape.UNKNOWN_KIND}
    assert {row["kind"] for row in _rows()} <= allowed


def test_the_list_is_ordered_by_the_seats_order_then_by_name(declared):
    """🔴 순서는 서버가 — `DECLARED_KINDS` 순, 그 밖(unknown)은 뒤, 같은 종류 안은 이름순.
    픽스처는 파일에 «거꾸로» 적혀 있어서, 받은 순서를 그대로 두면 이 줄이 빨개집니다."""
    rows = _rows()
    rank = {kind: i for i, kind in enumerate(rule_shape.DECLARED_KINDS)}
    keys = [(rank.get(row["kind"], len(rank)), str(row["name"])) for row in rows]
    assert keys == sorted(keys)
    assert [row["kind"] for row in rows][-1] == rule_shape.UNKNOWN_KIND


def test_the_seat_answers_a_raw_declaration_directly():
    assert rule_shape.declared_kind(REFUSED_JOIN) == "join"
    assert rule_shape.declared_kind({"derive": {"decide": {}}}) == "decide"
    assert rule_shape.declared_kind({"derive": "not a mapping"}) == rule_shape.UNKNOWN_KIND
    assert rule_shape.declared_kind(NONSENSE) == rule_shape.UNKNOWN_KIND
