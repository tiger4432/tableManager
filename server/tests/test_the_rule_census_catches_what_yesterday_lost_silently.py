"""사진 둘의 차이가 «2026-09-14 에 조용히 벌어진 일»을 말하는가 (S-234 0단계).

그날 잃은 것은 기능이 아니라 문장이었다 — 규칙 여덟이 돌고 있었는데 부팅 로그는 「8」만 찍었고,
모르는 칸 하나로 운영자의 선언이 «삭제»됐을 때 그것을 말하는 자리가 없었다. 이 파일은 그 자리가
말을 하는지 채점한다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chain import rule_census  # noqa: E402


def _rule(name, trigger="t", target="u", **extra):
    rule = {"name": name, "trigger_table": trigger, "target_table": target,
            "mapper": "m", "enabled": True}
    rule.update(extra)
    return rule


def _census(rules, origins=None):
    return rule_census.census(rules, origins)


def test_an_identical_set_says_so_rather_than_staying_quiet():
    """⛔ 침묵은 답이 아니다. 「같다」를 «말해야» 다음 단계를 밟을 근거가 된다."""
    before = _census([_rule("a"), _rule("b")])
    after = _census([_rule("a"), _rule("b")])

    diff = rule_census.census_diff(before, after)
    assert diff["same"] is True
    assert not diff["reordered"]
    assert "동일" in rule_census.describe(diff)


def test_a_rule_that_disappears_is_named():
    """🔴 그날의 사고 그 자체. S-152 의 거절이 규칙을 «버렸고», 무엇이 사라졌는지 말하는
    자리가 없었다. 이름이 나오지 않으면 이 계측기는 그날의 부팅 로그와 같은 것이다."""
    before = _census([_rule("keeper"), _rule("dropped_by_a_typo")])
    after = _census([_rule("keeper")])

    diff = rule_census.census_diff(before, after)
    assert diff["removed"] == ["dropped_by_a_typo"]
    assert diff["same"] is False
    assert "dropped_by_a_typo" in rule_census.describe(diff)


def test_a_rule_that_is_switched_off_is_not_the_same_as_one_that_is_gone():
    """⚠️ 두 사실은 «다르다». 꺼진 것은 선언에 남아 있고, 사라진 것은 없다.
    같은 칸에 담으면 운영자가 어느 파일을 열지 모른다."""
    before = _census([_rule("r")])
    after = _census([_rule("r", enabled=False)])

    diff = rule_census.census_diff(before, after)
    assert diff["removed"] == []
    assert diff["changed"][0]["name"] == "r"
    assert diff["changed"][0]["fields"]["enabled"] == {"before": True, "after": False}


def test_rewiring_a_rule_to_another_table_is_a_change():
    before = _census([_rule("r", trigger="dt_log", target="dt_inventory")])
    after = _census([_rule("r", trigger="dt_log", target="dt_job_attribution")])

    fields = rule_census.census_diff(before, after)["changed"][0]["fields"]
    assert fields["tables"]["after"]["target_table"] == "dt_job_attribution"


def test_a_table_key_beyond_the_obvious_two_is_photographed_too():
    """🔴 전 스위트가 잡은 결함. 표를 이름 대는 칸은 «일곱»이고, 처음 이 사진은 둘만 찍었다 —
    나머지로 배선이 바뀌면 「같다」고 답했을 것이다. 목록은 저자에게 묻는다."""
    keys = rule_census.table_keys()
    assert len(keys) > 2 and "map_table" in keys

    before = _census([_rule("r", map_table="dt_map")])
    after = _census([_rule("r", map_table="core_usage_map")])
    fields = rule_census.census_diff(before, after)["changed"][0]["fields"]
    assert fields["tables"]["after"]["map_table"] == "core_usage_map"


def test_narrowing_a_column_trigger_is_a_change_and_order_of_columns_is_not():
    """⚠️ 선언이 컬럼을 «적은 순서»는 이 축의 사실이 아니다 — 정렬해 비교한다.
    그러지 않으면 아무것도 안 바뀐 선언이 매번 「바뀜」으로 나오고, 그러면 아무도 안 본다."""
    before = _census([_rule("r", trigger_columns=["b_wy", "b_wx"])])
    same = _census([_rule("r", trigger_columns=["b_wx", "b_wy"])])
    assert rule_census.census_diff(before, same)["same"] is True

    narrowed = _census([_rule("r", trigger_columns=["b_wx"])])
    fields = rule_census.census_diff(before, narrowed)["changed"][0]["fields"]
    assert fields["trigger_columns"] == {"before": ["b_wx", "b_wy"], "after": ["b_wx"]}


def test_one_removal_does_not_report_every_later_rule_as_changed():
    """🔴 이 파일의 설계 요점. 위치로 짝지으면 하나가 빠질 때 뒤가 «전부» 밀려
    「전부 바뀜」이 되고, 진짜 사라진 하나가 소음에 묻힌다 — 그날 개수만 찍던 로그와 같은 병."""
    before = _census([_rule("a"), _rule("b"), _rule("c"), _rule("d")])
    after = _census([_rule("a"), _rule("c"), _rule("d")])

    diff = rule_census.census_diff(before, after)
    assert diff["removed"] == ["b"]
    assert diff["changed"] == []
    assert {entry["name"] for entry in diff["reordered"]} == {"c", "d"}


def test_a_synthesized_rule_says_it_was_not_written_by_the_operator():
    """🔴 「모든게 enable false 인데?」 의 답이 이 칸이다. 운영자가 쓴 파일에 «없는» 규칙이
    돌고 있었고, 사진이 그것을 구별하지 못하면 그 질문에 답할 수 없다."""
    rules = [_rule("mine"), _rule("enrichment_dedup:x")]
    rows = _census(rules, origins={"enrichment_dedup:x": "synthesized"})

    by_name = {row["name"]: row for row in rows}
    assert by_name["mine"]["origin"] == "declared"
    assert by_name["enrichment_dedup:x"]["origin"] == "synthesized"


def test_the_derive_axis_is_read_off_a_rule_the_loader_actually_produces():
    """🔴 [판정 501 ⓒ] THIS TEST WAS VACUOUS, AND THAT IS WHY THE BOOT LINE LIED.

    It fed `derive_kind` shapes with `right_table` / `decision_key` / `derive` at the TOP
    LEVEL - cells `expand_declaration` does not leave on a loaded rule - so every assertion
    passed against inputs the product never makes, while every REAL loaded rule came back
    「mapper」. An operator who declared a join, restarted and searched the boot line
    `[ChainRules] set(N): 이름[출처,방식]` for `join` found nothing, while the retroactive
    banner called the same rule `kind: "join"`.
    ⚠️ 「범례가 단언을 공허하게 만든다」 exactly: the fixture fed the assertion.

    🔴 SO THE FIXTURE IS THE PRODUCT'S OWN OUTPUT NOW. `expand_declaration` stands the
    declaration an operator writes, and the label is read off what it produced.
    """
    from chain import rule_shape
    from database import crud

    stood, refusal, _notes = rule_shape.expand_declaration(
        {"name": "inv", "on": {"table": "dt_inventory"},
         "derive": {"kind": "join",
                    "join": {"right_table": "dt_job_attribution",
                             "on": [{"left": "dt_job", "right": "dt_job"}],
                             "take": ["dt_lot_confirmed"]}},
         "into": {"table": "dt_inventory"}},
        crud.TABLE_CONFIG)

    assert refusal is None, refusal
    assert stood, "the declaration stood no rules, so this asserts nothing"
    for rule in stood:
        assert rule_census.derive_kind(rule) == "join", (
            "a rule the loader produced from a JOIN declaration is labelled %r - and that is "
            "the word the boot line puts in front of the operator"
            % rule_census.derive_kind(rule))

    # ⚠️ THE OTHER WORDS, AND THE GAP. A plain file mapper is 「mapper」; a rule naming no code
    #    at all is 「unknown」, which is a different fact from 「a mapper we do not know」.
    assert rule_census.derive_kind({"mapper_module": "m", "mapper_function": "f"}) == "mapper"
    assert rule_census.derive_kind({}) == "unknown"
    assert rule_census.derive_kind(None) == "unknown"
