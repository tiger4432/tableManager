"""왕복 동일성 — 통합 2단계의 «유일한» 증거 (S-234 8.3 ②).

내부 객체가 오늘의 선언을 받아 오늘의 소비자에게 돌려줄 때 «같은 dict» 가 아니면, 로더를
내부 객체로 갈아 끼우는 다음 단계는 동작 0 이 아니라 «희망»이 된다. 2026-09-14 의 사고 넷은
전부 「같을 줄 알았다」였다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chain import rule_shape  # noqa: E402


CHAIN_RULES = [
    {"name": "plain", "trigger_table": "dt_log", "target_table": "dt_inventory",
     "mapper": "frame_map"},
    {"name": "full", "enabled": False, "trigger_table": "dt_log",
     "trigger_columns": ["b_wx", "b_wy"], "target_table": "dt_map",
     "mapper_module": "m", "mapper_function": "f", "params": {"gate": 7},
     "group_by": ["lot"], "max_group_rows": 1000, "max_group_attempts": 2,
     "idempotent": True},
    # 🔴 이 모듈이 «모르는» 칸을 든 규칙. 운영 선언은 언제나 이렇게 생겼다 —
    #    맵퍼가 읽는 납작한 칸은 gitignore 된 파일에 사는 코드가 읽으므로 제품은 뜻을 모른다.
    {"name": "unknown_cells", "trigger_table": "t", "target_table": "u",
     "mapper": "m", "allow_chain_trigger": True, "follow_up": False,
     "some_mapper_argument": "값", "another": [1, 2, 3]},
    # ⚠️ `enabled` 가 «없는» 규칙과 «참으로 적힌» 규칙은 다른 문장이다
    {"name": "enabled_written", "enabled": True, "trigger_table": "t",
     "target_table": "u", "mapper": "m"},
]

JOIN_RULES = [
    ("slot_trace", {"left_table": "dt_log", "right_table": "dt_inventory",
                    "left_columns": ["lot", "slot"], "right_columns": ["lot", "slot"],
                    "cardinality": "one", "expose": ["grade"]}),
    ("folded", {"left_table": "a", "right_table": "b",
                "left_columns": ["k"], "right_columns": ["k"],
                "right_folds": [["strip", "upper"]], "cardinality": "one",
                "materialize": True, "rewrite_cap": 10000}),
]


def test_every_chain_rule_comes_back_byte_for_byte():
    """🔴 이 단언이 초록이어야 다음 단계가 «정의상» 동작 0 이다."""
    for raw in CHAIN_RULES:
        back = rule_shape.as_chain_rule(rule_shape.from_chain_rule(raw))
        assert back == raw, (raw.get("name"), back, raw)


def test_every_join_rule_comes_back_byte_for_byte():
    for name, raw in JOIN_RULES:
        back = rule_shape.as_join_rule(rule_shape.from_join_rule(name, raw))
        assert back == raw, (name, back, raw)


def test_an_absent_enabled_does_not_become_a_written_one():
    """⚠️ 「안 적음」과 「true 라고 적음」은 다른 선언이다. 왕복이 칸을 «만들면» 그 선언은
    내가 쓴 것이 아니게 되고, diff 는 매번 「바뀜」이라 말한다."""
    raw = {"name": "r", "trigger_table": "t", "target_table": "u", "mapper": "m"}
    assert "enabled" not in rule_shape.as_chain_rule(rule_shape.from_chain_rule(raw))


def test_the_unknown_cells_survive_and_are_named_as_unknown():
    """🔴 모르는 칸을 «버리지 않는다». 제품이 뜻을 모르는 칸(맵퍼 인자)은 운영 선언의
    정상적인 절반이고, 2026-09-14 에 그것을 거절로 다룬 것이 선언을 삭제했다."""
    raw = dict(CHAIN_RULES[2])
    internal = rule_shape.from_chain_rule(raw)

    assert internal["extra"]["some_mapper_argument"] == "값"
    assert internal["extra"]["another"] == [1, 2, 3]
    assert rule_shape.as_chain_rule(internal) == raw


def test_the_shape_says_what_it_derives_with_and_where_it_lands():
    """통합이 접으려는 축 둘이 «칸»으로 서 있는가."""
    chain = rule_shape.from_chain_rule(CHAIN_RULES[0])
    assert chain["derive"]["kind"] == "mapper"
    assert chain["into"] == {"table": "dt_inventory"}

    join = rule_shape.from_join_rule(*JOIN_RULES[0])
    assert join["derive"]["kind"] == "join"
    assert join["into"] == {"read": True}
    assert join["derive"]["join"]["right_table"] == "dt_inventory"


def test_the_column_trigger_rides_on_the_on_clause():
    internal = rule_shape.from_chain_rule(CHAIN_RULES[1])
    assert internal["on"] == {"table": "dt_log", "columns": ["b_wx", "b_wy"]}


# ---------------------------------------------------------------------------
# 출하 선언 «전건» — 제 손으로 만든 dict 는 제가 아는 모양만 담는다
# ---------------------------------------------------------------------------

import json  # noqa: E402

_SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "sample")


def _shipped(filename):
    with open(os.path.join(_SAMPLE_DIR, filename), encoding="utf-8") as handle:
        return json.load(handle)


def test_every_shipped_chain_rule_survives_the_round_trip():
    """🔴 손으로 만든 픽스처는 «내가 아는 모양»만 담는다. 2026-09-14 에 뷰 픽스처가
    결함을 «표현할 수 없어» 초록이었던 것이 그 병이고, 여기서는 출하되는 선언 전건을 태운다."""
    document = _shipped("chain_rules.json.sample")
    rules = document.get("rules", document)
    rules = rules if isinstance(rules, list) else list(rules.values())
    assert rules, "출하 체인 선언이 비어 있으면 이 게이트는 공허하다"

    for raw in rules:
        if not isinstance(raw, dict):
            continue
        back = rule_shape.as_chain_rule(rule_shape.from_chain_rule(raw))
        assert back == raw, raw.get("name")


def test_every_shipped_join_declaration_survives_the_round_trip():
    document = _shipped("virtual_join_rules.json.sample")
    declarations = {name: raw for name, raw in document.items()
                    if isinstance(raw, dict) and not name.startswith("_")}
    assert declarations, "출하 조인 선언이 비어 있으면 이 게이트는 공허하다"

    for name, raw in declarations.items():
        back = rule_shape.as_join_rule(rule_shape.from_join_rule(name, raw))
        assert back == raw, name


# ---------------------------------------------------------------------------
# 새 문법 — 「옛것 -> 새 문법 -> 옛것」이 같아야 이행이 무손실이다 (S-234 8.3 ④)
# ---------------------------------------------------------------------------

def test_a_chain_rule_written_in_the_new_grammar_comes_back_as_itself():
    """🔴 이행의 게이트. 새 문법으로 «적어 두고» 다시 읽었을 때 오늘의 소비자가 받는 dict 가
    원본과 달라지면, 3단계(기계가 파일을 옮겨 씀)는 선언을 조용히 바꾸는 것이 된다."""
    for raw in CHAIN_RULES:
        written = rule_shape.to_declaration(rule_shape.from_chain_rule(raw))
        back = rule_shape.as_chain_rule(rule_shape.from_declaration(written))
        assert back == raw, (raw.get("name"), written, back)


def test_a_join_written_in_the_new_grammar_comes_back_as_itself():
    for name, raw in JOIN_RULES:
        written = rule_shape.to_declaration(rule_shape.from_join_rule(name, raw))
        back = rule_shape.as_join_rule(rule_shape.from_declaration(written))
        assert back == raw, (name, written, back)


def test_every_shipped_declaration_survives_the_new_grammar():
    """출하 선언 전건으로 같은 것을 다시 — 이행이 붙을 대상이 바로 이것들이다."""
    document = _shipped("chain_rules.json.sample")
    rules = document.get("rules", document)
    rules = rules if isinstance(rules, list) else list(rules.values())
    for raw in rules:
        if not isinstance(raw, dict):
            continue
        written = rule_shape.to_declaration(rule_shape.from_chain_rule(raw))
        assert rule_shape.as_chain_rule(rule_shape.from_declaration(written)) == raw, \
            raw.get("name")

    joins = {name: raw for name, raw in _shipped("virtual_join_rules.json.sample").items()
             if isinstance(raw, dict) and not name.startswith("_")}
    for name, raw in joins.items():
        written = rule_shape.to_declaration(rule_shape.from_join_rule(name, raw))
        assert rule_shape.as_join_rule(rule_shape.from_declaration(written)) == raw, name


def test_the_new_grammar_does_not_invent_empty_cells():
    """⚠️ «없는 것»과 «비어 있게 정한 것»은 다른 문장이다. 빈 limits 를 적어 두면
    운영자가 「무언가 설정돼 있다」고 읽는다."""
    written = rule_shape.to_declaration(rule_shape.from_chain_rule(CHAIN_RULES[0]))
    assert "limits" not in written
    assert "enabled" not in written
    assert written["on"] == {"table": "dt_log"}


# ---------------------------------------------------------------------------
# 미리보기 도구 — «깨지면 안 쓴다» 가 그 도구의 전부다
# ---------------------------------------------------------------------------

def test_the_preview_refuses_to_write_when_a_declaration_would_not_round_trip(tmp_path,
                                                                             monkeypatch):
    """🔴 반쯤 옳은 이행 파일은 없느니만 못하다. 하나라도 왕복이 깨지면 «쓰지 않고», 그
    선언을 이름으로 든다. 이 경로를 안 태우면 그것은 「돈다고 믿는 거절」이다."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import preview_unified_declarations as preview

    config = tmp_path / "config"
    config.mkdir()
    (config / "chain_rules.json").write_text(json.dumps({"rules": [
        {"name": "ok", "trigger_table": "t", "target_table": "u", "mapper": "m"}]}),
        encoding="utf-8")

    document, report = preview.build(str(config))
    assert report["broken"] == []
    assert report["count"] == 1
    assert report["kinds"] == {"mapper→table": 1}

    # 왕복을 «고의로» 깨뜨린다 — 어댑터가 칸 하나를 잃는 세상에서 도구가 무엇을 하는가
    monkeypatch.setattr(preview.rule_shape, "as_chain_rule",
                        lambda internal: {"name": internal.get("name")})
    document, report = preview.build(str(config))
    assert report["broken"] == [("chain", "ok")]
    assert preview.main(["--config", str(config),
                         "--out", str(tmp_path / "never.json")]) == 1
    assert not (tmp_path / "never.json").exists()
