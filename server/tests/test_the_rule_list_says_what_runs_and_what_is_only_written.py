# -*- coding: utf-8 -*-
"""판정 644 · 656 — 규칙 목록이 «도는 것»과 «적혀만 있는 것»을 둘 다, 갈라서 답한다.

> 소유자: 644 의 세 안 중 「ㄱ」 — 꺼 둔 규칙이 목록에서 사라지지 않게

🔴 THE DEFECT. `GET /admin/chain/rules` handed back the FILE. The loader SYNTHESISES rules
that are written nowhere in it - an enrich declaration's two halves, a join's `:reference`
companion - so those were invisible on the one screen that claims to list every rule, while
the cycle warning right beside it named them. 617's third symptom.

🔴 AND THE REPAIR HAD A TRAP, MEASURED BEFORE IT WAS WRITTEN (판정 654 -> 656). Sending the
route to the loader ALONE drops the other half: a unified declaration carrying `enabled:
false` stands no rule, so an operator who switched one off could no longer see it on the
screen they would use to switch it back on. Removing the early return that does that was
tried and reverted - it does not make the declaration stand (a second seat in
`chain/enrichment/config` refuses it) and it revives 판정 399's incident, because switching
a declaration off currently doubles as exemption from validation and the box's own
switched-off declaration is an UNFINISHED one that then errors on every load.

⚠️ SO THE TWO STATES ARE CARRIED, NOT MERGED. `rule_state` says which, `rule_state_detail`
says why, and 「없다」 never shares a pixel with 「꺼짐」.

⛔ AND THE CELL IS `rule_state`, NOT `state`, BECAUSE THE ANSWER ALREADY OWNS THAT WORD.
`listing_absence.absent_listing` puts `state: absent` on the ENVELOPE - a different subject
(the file) at a different level (the answer, not a row). Spelling both `state` would give one
word two meanings across two scopes, and the client already reads the envelope's.
"""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain.enrichment import config as enrichment_config            # noqa: E402
from database import crud                                           # noqa: E402

SRC, DST = "r644_src", "r644_derived"

#: 선 규칙이 «파일에 없는 이름»으로 뜨는 선언 — 이 파일의 주제.
DECIDE = {"name": "r644_decide", "on": {"table": SRC}, "into": {"table": DST},
          "derive": {"kind": "decide", "decide": {
              "key": ["job"], "fields": ["grade"], "auto_confirm": True}}}

#: 꺼 둔 «통합» 선언 — 로더에는 안 서고, 목록에는 서야 한다.
OFF = {"name": "r644_off", "enabled": False,
       "on": {"table": SRC}, "into": {"table": DST},
       "derive": {"kind": "decide", "decide": {"key": ["job"], "fields": ["grade"]}}}

#: 꺼 둔 «평면» 규칙 — 오늘도 로더가 들고 나온다. 회귀 칸.
FLAT_OFF = {"name": "r644_flat_off", "enabled": False,
            "trigger_table": SRC, "target_table": DST,
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
    flat = tmp_path / "enrichment_rules.json"
    flat.write_text(json.dumps({}), encoding="utf-8")
    chain_file = tmp_path / "chain_rules.json"
    chain_file.write_text(json.dumps({"rules": [DECIDE, OFF, FLAT_OFF]}), encoding="utf-8")

    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(flat))
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))
    enrichment_config._RULES_MEMO.clear()
    crud.TABLE_CONFIG.update(TABLES)

    import paths
    real_config_path = paths.config_path
    monkeypatch.setattr(paths, "config_path",
                        lambda name: (str(chain_file) if name == "chain_rules.json"
                                      else real_config_path(name)))
    try:
        yield
    finally:
        enrichment_config._RULES_MEMO.clear()
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _listing():
    import main

    answer = main.get_chain_rules()
    assert answer["status"] == "success", answer
    return {row["name"]: row for row in answer["data"]}


# ---------------------------------------------------------------------------
# ⓐ 「돈다」 — 파일에 «없는» 이름이 목록에 선다 (617 의 증상)
# ---------------------------------------------------------------------------

def test_the_halves_the_product_synthesised_are_on_the_list(declared):
    """🔴 이 넷은 `chain_rules.json` 어디에도 «안 적혀» 있습니다. 로더가 세웁니다."""
    rows = _listing()

    assert "enrichment_dedup:r644_decide" in rows
    assert "enrichment_auto_confirm:r644_decide" in rows
    for name in ("enrichment_dedup:r644_decide", "enrichment_auto_confirm:r644_decide"):
        assert rows[name]["rule_state"] == event_constants.RULE_STATE_RUNNING, name

    assert "r644_decide" not in rows, (
        "선언 «이름»은 목록에 서지 않습니다 — 반쪽 둘로 갈려 섭니다")


def test_a_running_row_carries_the_cells_the_screen_draws(declared):
    """⚠️ 공허 방지. 「떴다」만으로는 화면이 «빈 행»을 그려도 초록입니다."""
    row = _listing()["enrichment_dedup:r644_decide"]

    assert row.get("trigger_table") == SRC
    assert row.get("target_table") == DST
    assert row.get("mapper"), "맵퍼 칸이 비면 화면의 그 열이 빕니다"


# ---------------------------------------------------------------------------
# 🔴 ⓑ 「적혀만 있다」 — 판정 656 의 주제
# ---------------------------------------------------------------------------

def test_a_switched_off_unified_declaration_stays_on_the_list(declared):
    """⚰️ 이 줄이 654->656 의 이유입니다. 로더만 부르면 이 선언은 «사라지고», 끈 운영자는
    다시 켜러 갈 화면에서 그것을 못 찾습니다."""
    rows = _listing()

    assert "r644_off" in rows, "꺼 둔 통합 선언이 목록에서 사라졌습니다"
    assert rows["r644_off"]["rule_state"] == event_constants.RULE_STATE_DECLARED_ONLY
    assert "enabled=false" in (rows["r644_off"].get("rule_state_detail") or ""), (
        "왜 안 섰는지를 «옆에서» 말해야 합니다 — 상태값만으로는 꺼짐과 미완성이 같습니다")


def test_running_and_declared_only_never_share_a_pixel(declared):
    """🔴 [판정 656] 「없다」와 「꺼짐」이 같은 픽셀이면 이 라운드가 한 일이 없습니다."""
    rows = _listing()

    states = {name: row["rule_state"] for name, row in rows.items()}
    assert states["r644_off"] != states["enrichment_dedup:r644_decide"]
    assert set(states.values()) <= event_constants.RULE_STATES


def test_a_rule_the_loader_refused_is_on_the_list_too(declared, tmp_path, monkeypatch):
    """⚰️ 제 첫 판별식이 «틀렸던» 자리입니다. 「선다」를 문법에만 물었더니, 문법은 세우고
    로더가 «거절»하는 규칙(맵퍼를 못 찾는 평면 규칙)이 목록에서 통째로 사라졌습니다 —
    적어 놓고 안 도는 것이 「적어 둔 적 없는 것」과 같은 픽셀이 됐습니다.

    🔴 그래서 판별식이 «둘»을 지납니다: 어떤 이름으로 설지는 문법이, 정말 서는지는 로더가."""
    broken = {"name": "r644_no_mapper", "trigger_table": SRC, "target_table": DST}
    chain_file = tmp_path / "refused.json"
    chain_file.write_text(json.dumps({"rules": [broken]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))

    import paths
    monkeypatch.setattr(paths, "config_path", lambda name: str(chain_file))

    rows = _listing()

    assert "r644_no_mapper" in rows, "로더가 거절한 규칙이 목록에서 사라졌습니다"
    assert rows["r644_no_mapper"]["rule_state"] == event_constants.RULE_STATE_DECLARED_ONLY


def test_one_half_falling_does_not_hide_behind_the_other(declared, tmp_path, monkeypatch):
    """⚰️ [Q-191] 한 선언이 «이름이 다른» 규칙 둘을 세우고, 로더는 «이름으로» 떨어뜨립니다
    (`name_claimed_twice`). 그래서 반쪽 하나만 떨어질 수 있습니다 — 제 첫 판별식은
    「이 선언에서 «무엇이든» 섰나」를 물어 그것을 「돈다」로 접었고, 떨어진 반쪽은 화면
    어디에도 안 떴습니다. 644 가 닫으려던 결함이 한 줄 아래에서 되살아난 모양입니다."""
    clash = {"name": "enrichment_auto_confirm:r644_half", "trigger_table": DST,
             "target_table": DST, "mapper_module": "m", "mapper_function": "f"}
    half = {"name": "r644_half", "on": {"table": SRC}, "into": {"table": DST},
            "derive": {"kind": "decide", "decide": {"key": ["job"], "fields": ["grade"]}}}
    chain_file = tmp_path / "half.json"
    chain_file.write_text(json.dumps({"rules": [half, clash]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))

    import paths
    monkeypatch.setattr(paths, "config_path", lambda name: str(chain_file))

    rows = {}
    for row in __import__("main").get_chain_rules()["data"]:
        rows.setdefault(row["name"], row)

    assert rows["enrichment_dedup:r644_half"]["rule_state"] == \
        event_constants.RULE_STATE_RUNNING, "선 반쪽은 돌아야 합니다"
    # ⚠️ 「목록에 있다」만 단언하면 공허합니다 — 안 떨어졌어도 running 으로 «있기» 때문입니다.
    #    떨어졌다는 사실 자체를 단언해야 이 줄이 결함을 잽니다.
    assert rows["enrichment_auto_confirm:r644_half"]["rule_state"] == \
        event_constants.RULE_STATE_DECLARED_ONLY, (
            "떨어진 반쪽이 «형제 뒤에 숨었습니다» — 목록이 규칙 전부를 못 보여 줍니다")


def test_a_switched_off_flat_rule_is_unchanged(declared):
    """⚠️ 회귀 칸. 평면은 로더가 오늘도 «들고 나옵니다» — 이쪽을 건드리지 않았습니다."""
    row = _listing()["r644_flat_off"]

    assert row["rule_state"] == event_constants.RULE_STATE_RUNNING
    assert row.get("enabled") is False, (
        "「목록에 있다」와 「돈다」는 다른 사실이고, 그 구분은 `enabled` 가 계속 나릅니다")


def test_switching_it_back_on_moves_it_to_running(declared, tmp_path, monkeypatch):
    """🔴 [판정 656 게이트 ②] 켜면 «사라지지 않고» 돈다로 바뀐다 — 목록이 그 왕복을 답한다."""
    on = dict(OFF)
    on.pop("enabled")
    chain_file = tmp_path / "back_on.json"
    chain_file.write_text(json.dumps({"rules": [on]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))

    import paths
    monkeypatch.setattr(paths, "config_path", lambda name: str(chain_file))

    rows = _listing()

    assert "r644_off" not in rows
    assert rows["enrichment_dedup:r644_off"]["rule_state"] == event_constants.RULE_STATE_RUNNING


# ---------------------------------------------------------------------------
# ⓒ 「없는 파일」 — 건드리지 않았다
# ---------------------------------------------------------------------------

def test_a_missing_file_still_answers_absent_not_empty(tmp_path, monkeypatch):
    """⛔ 644 가 ⚠️ 로 적은 그대로. absent ≠ empty — 빈 목록으로 접으면 운영자가
    「규칙이 없구나」로 읽습니다."""
    import main
    import paths

    missing = tmp_path / "not_here.json"
    monkeypatch.setattr(paths, "config_path", lambda name: str(missing))
    monkeypatch.setattr(worker, "RULES_PATH", str(missing))

    answer = main.get_chain_rules()

    import listing_absence

    assert answer["state"] == listing_absence.LISTING_ABSENT, answer
    assert answer["absent_path"] == str(missing), answer
    assert answer["data"] == [], answer
