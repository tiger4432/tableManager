# -*- coding: utf-8 -*-
"""판정 678 ① · 680 — 「조인 승인」이 실조인 좌석에서 답한다.

🔴 THE AXIS LIVES, THE PLUMBING WORD DIES. 「승인 = 조인 키를 덮는 UNIQUE 인덱스가 «실제로»
있다」 is carried by the REAL join; only the spelling 「virtual-join」 belongs to the grammar
being retired. So the route name moves and the question does not, and this file scores the
question at its new seat.

⚠️ ONE AUTHOR, THREE QUESTIONS. 「which index do we build」·「which do we require」·「which do
we report」 all come out of `declared_unique_targets`, for the reason its own docstring gives:
the day two of them disagree, the product builds an index at warmup and retracts it on the
next read, forever.

🔴 AND THE OLD ROUTE IS STILL STANDING WHILE THIS ONE IS. Deleting it before the client calls
the new seat would make the screen draw 「모름」 forever without throwing (판정 672) - so the
cell-identity row below compares this report's SHAPE against the old one's, live, rather than
against a list I typed.
"""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import join_key_index, synthesis                          # noqa: E402

MAP_COLS = {"lot": "string", "slot": "string", "dt_job": "string",
            "dt_lot": "string", "dt_slot": "string", "wafer_id": "string"}

TABLES = {
    "a678_log": {"business_key": "k", "composite_key_source": ["lot", "slot"],
                 "column_types": dict(MAP_COLS)},
    "a678_inventory": {"business_key": "k", "composite_key_source": ["dt_job"],
                       "column_types": dict(MAP_COLS)},
}


def _join(name, unique=True, enabled=True, right="a678_inventory"):
    """실제 선언(`inventory_confirmed`)과 «같은 모양». 손으로 지은 모양이 아니다."""
    declaration = {
        "name": name,
        "on": {"table": "a678_log"},
        "derive": {"kind": "join", "join": {
            "right_table": right,
            "on": [{"left": "dt_job", "right": "dt_job"}],
            "take": ["dt_lot", "dt_slot"]}},
        "into": {"table": "a678_log"},
    }
    if unique:
        declaration["key"] = {"unique": True}
    if not enabled:
        declaration["enabled"] = False
    return declaration


@pytest.fixture(autouse=True)
def _fresh():
    synthesis.reset_right_key_cache()
    yield
    synthesis.reset_right_key_cache()


def _document(monkeypatch, declarations, covering=True, probes=None):
    from chain import ingestion_worker

    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda *a, **kw: {"exists": True, "error": None,
                                          "rules": list(declarations)})

    def fake_covering(db, table, columns, folds=None):
        if probes is not None:
            probes.append((table, tuple(columns)))
        return "uq_a678" if covering else None

    monkeypatch.setattr(join_key_index, "unique_index_covering", fake_covering)


def _by_name(report):
    return {row["name"]: row for row in report["declarations"]}


# ---------------------------------------------------------------------------
# ⓐ 승인 — 두 방향
# ---------------------------------------------------------------------------

def test_a_declared_key_with_a_real_index_is_accepted(monkeypatch):
    _document(monkeypatch, [_join("a678_ok")])

    report = synthesis.approval_report(None, known_tables=TABLES)
    row = _by_name(report)["a678_ok"]

    assert row["accepted"] is True
    assert row["unique_index"] == "uq_a678"
    assert row["detail"] is None
    assert row["required_index_ddl"] is None, (
        "승인된 조인에 DDL 을 실으면 운영자가 «이미 있는» 인덱스를 또 만듭니다")
    assert report["accepted"] == 1 and report["refused"] == 0


def test_a_declared_key_without_an_index_says_what_to_run(monkeypatch):
    """⛔ 거절은 «다음 행동»을 실어야 합니다. 그리고 그 문장은 `/admin/config/resolve` 와
    같은 조립기가 짓습니다 — 갈라 두면 같은 거부가 두 화면에서 다른 문장이 됩니다."""
    _document(monkeypatch, [_join("a678_bad")], covering=False)

    row = _by_name(synthesis.approval_report(None, known_tables=TABLES))["a678_bad"]

    assert row["accepted"] is False
    assert row["unique_index"] is None
    assert "CREATE UNIQUE INDEX" in (row["required_index_ddl"] or "")
    assert row["detail"] and "a678_inventory" in row["detail"]
    assert "no valid UNIQUE index" not in row["detail"], "영어 로더 문구가 샜습니다"


# ---------------------------------------------------------------------------
# 🔴 ⓑ 모집단 — 판정 680. 「안 물었다」도 «답»이고, 그 답이 말을 해야 한다
# ---------------------------------------------------------------------------

def test_a_join_that_declares_no_uniqueness_is_listed_with_its_reason(monkeypatch):
    """🔴 [판정 680] 걷는 이가 이 칸을 «그냥 지나갔습니다». 꺼진 조인은 사유와 함께 나오고
    유일성을 안 적은 조인은 «조용»했으니, 한 축에서 한 비답만 말을 한 것입니다. 그 침묵은
    운영자에게 「제품이 내 선언을 안 읽었다」와 «같은 모양»입니다."""
    _document(monkeypatch, [_join("a678_nokey", unique=False)])

    report = synthesis.approval_report(None, known_tables=TABLES)
    row = _by_name(report)["a678_nokey"]

    assert row["accepted"] is False
    assert row["detail"] and "key.unique" in row["detail"], row["detail"]
    assert row["unique_index"] is None


def test_declaring_no_uniqueness_still_builds_and_requires_nothing(monkeypatch):
    """⚠️ 680 의 ㄴ 이 «인덱스를 만들지 않는다»는 것. 사유를 내는 것과 요구하는 것은 다른
    일이고, 이 줄이 없으면 「보고하려고」 인덱스가 생기는 회귀를 아무도 안 잡습니다."""
    from chain import ingestion_worker

    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda *a, **kw: {"exists": True, "error": None,
                                          "rules": [_join("a678_nokey", unique=False)]})

    assert synthesis.declared_unique_index_names(known_tables=TABLES) == set()


def test_a_switched_off_join_is_listed_rather_than_missing(monkeypatch):
    """🔴 꺼 둔 선언은 서는 규칙이 «0» 이라 걷는 이에 닿지 않습니다 (판정 399). 여기서도
    빠지면 운영자가 자기 선언을 화면에서 «못 찾습니다» — 판정 680 이 메운 그 구멍입니다."""
    _document(monkeypatch, [_join("a678_off", enabled=False)])

    report = synthesis.approval_report(None, known_tables=TABLES)
    row = _by_name(report)["a678_off"]

    assert row["accepted"] is False
    assert row["detail"] and "enabled=false" in row["detail"]
    assert report["invalid"] == [], "끈 것은 «틀린 것»이 아닙니다 (판정 399)"


# ---------------------------------------------------------------------------
# 🔴 Ⓑ-2 상태 칸 — 판정 685. 화면이 «유도»하면 안 된다
# ---------------------------------------------------------------------------

def test_each_row_carries_one_of_three_states_and_nothing_else(monkeypatch):
    """⚠️ 닫힌 어휘다. 열려 있으면 화면이 모르는 값을 만나 «조용히» 아무것도 안 그린다."""
    import event_constants

    nokey = _join("a678_nokey", unique=False)
    off = _join("a678_off", enabled=False)
    _document(monkeypatch, [_join("a678_ok"), nokey, off])

    report = synthesis.approval_report(None, known_tables=TABLES)
    states = {row["name"]: row["approval_state"] for row in report["declarations"]}

    assert set(states.values()) <= event_constants.APPROVAL_STATES, states
    assert states["a678_ok"] == event_constants.APPROVAL_STATE_APPROVED
    assert states["a678_nokey"] == event_constants.APPROVAL_STATE_NOT_ASKED
    # ⛔ [판정 399] 끈 것은 «틀린 것이 아니다». 거절로 그리면 운영자가 자기가 «고쳐야 할
    #    것»으로 읽고, 고칠 것이 없다.
    assert states["a678_off"] == event_constants.APPROVAL_STATE_NOT_ASKED


def test_a_refusal_without_a_ddl_is_still_a_refusal(monkeypatch):
    """🔴 [판정 685] 이 줄이 이 라운드의 «이유»다. 클라는 「required_index_ddl 이 있나」로
    「안 물음」과 「거절」을 가르고 있었다 — 대리다. DDL 이 «없는» 거절이 하나라도 있으면 그
    화면은 조용히 틀린다. 여기가 그 하나다: 오른쪽 키가 없으면 만들 DDL 이 아예 없다.

    ⚠️ 그리고 이 행과 「안 물음」 행은 `accepted`·`detail`·`required_index_ddl` 이 «전부 같다».
    가를 수 있는 칸은 `approval_state` 뿐이다.
    """
    import event_constants

    broken = _join("a678_nokeypair")
    broken["derive"]["join"]["on"] = []          # 키 쌍이 없다 -> 덮을 오른쪽 키가 없다
    _document(monkeypatch, [broken, _join("a678_nokey", unique=False)])

    rows = _by_name(synthesis.approval_report(None, known_tables=TABLES))
    refused, not_asked = rows["a678_nokeypair"], rows["a678_nokey"]

    assert refused["approval_state"] == event_constants.APPROVAL_STATE_REFUSED
    assert not_asked["approval_state"] == event_constants.APPROVAL_STATE_NOT_ASKED
    for cell in ("accepted", "required_index_ddl", "unique_index", "required_index"):
        assert refused[cell] == not_asked[cell], (
            "%s 로는 둘을 못 가립니다 — 그래서 상태 칸이 필요합니다" % cell)


def test_the_state_follows_the_kind_cell_and_not_the_sentence(monkeypatch):
    """🔴 [판정 685] 「⛔ 사유 «문장»으로 가르지 마십시오 — 그건 자리를 세는 것입니다」.

    ⚠️ 이 줄이 없을 때 «문장을 보는» 변이가 초록으로 통과했습니다 — 앞 줄들은 상태가 «맞는지»만
    재고 «어디서 왔는지»는 안 쟀기 때문입니다. 그래서 여기서는 사유를 알아볼 수 없는 문장으로
    바꿔 두고 상태가 «칸»을 따라가는지 봅니다. 낱말이 바뀌는 날 조용히 틀리는 것이 이 부류입니다.
    """
    import event_constants

    _document(monkeypatch, [_join("a678_x"), _join("a678_y")])
    monkeypatch.setattr(
        synthesis, "declared_unique_targets",
        lambda rules: [("a678_x", None, None, None, "…", synthesis.SKIP_UNMET),
                       ("a678_y", None, None, None, "…", synthesis.SKIP_NOT_ASKED)])

    rows = _by_name(synthesis.approval_report(None, known_tables=TABLES))

    assert rows["a678_x"]["approval_state"] == event_constants.APPROVAL_STATE_REFUSED
    assert rows["a678_y"]["approval_state"] == event_constants.APPROVAL_STATE_NOT_ASKED


# ---------------------------------------------------------------------------
# ⓒ 거절 — 갈래를 가려서 싣는다
# ---------------------------------------------------------------------------

def test_a_refused_join_declaration_lands_in_invalid(monkeypatch):
    bad = _join("a678_refused")
    bad["into"] = {"read": True}                       # 읽기 시점 조인 = 은퇴한 능력
    _document(monkeypatch, [bad])

    report = synthesis.approval_report(None, known_tables=TABLES)

    # 🔴 [판정 686] 652 의 남긴다 항목은 「읽기 시점 조인은 «이름 대어» 거절」이다.
    #    「invalid 에 들었다」만 재면 반쪽이고, 운영자가 화면에서 보는 것은 «문장»이다.
    assert [item["subject"] for item in report["invalid"]] == ["a678_refused"]
    assert "a678_refused" in (report["invalid"][0]["detail"] or ""), (
        "거절이 자기 «이름»을 안 댑니다: %r" % (report["invalid"][0]["detail"],))
    assert report["declarations"] == []


def test_a_refused_declaration_of_another_kind_is_not_on_this_panel(monkeypatch):
    """⚠️ 거절된 `decide` 를 「조인 승인」에 실으면 운영자가 이 화면에서 «못 고치는» 것을
    이 화면에서 읽습니다. 갈래는 선언이 «자기 낱말»로 말합니다."""
    bad_decide = {"name": "a678_decide", "on": {"table": "a678_log"},
                  "derive": {"kind": "decide", "decide": {"nonsense_cell": 1}},
                  "into": {"table": "a678_log"}}
    _document(monkeypatch, [_join("a678_ok"), bad_decide])

    report = synthesis.approval_report(None, known_tables=TABLES)

    assert [item["subject"] for item in report["invalid"]] == []
    assert list(_by_name(report)) == ["a678_ok"]


# ---------------------------------------------------------------------------
# ⓓ 한 사실, 한 문장 · 지금의 답 · 옛 라우트와 같은 칸
# ---------------------------------------------------------------------------

def test_one_uniqueness_is_one_row_even_though_two_rules_stand(monkeypatch):
    """⚠️ 조인과 그 `:reference` 짝은 «같은 키»를 선언합니다. 둘로 두면 운영자가 한 인덱스를
    두 줄로 읽고, 패널의 수가 «인덱스의 수»와 안 맞습니다."""
    probes = []
    _document(monkeypatch, [_join("a678_ok")], probes=probes)

    report = synthesis.approval_report(None, known_tables=TABLES)

    assert len(report["declarations"]) == 1, report["declarations"]
    assert len(probes) == 1, "같은 인덱스를 두 번 물었습니다: %r" % (probes,)


def test_the_report_answers_now_and_not_out_of_the_write_gates_cache(monkeypatch):
    """🔴 [판정 680 ⓑ] 운영자가 인덱스를 «방금 만들고» 새로고침하는 자리라 답이 «지금»
    이어야 합니다. 같은 워커와 같은 탐침을 쓰므로 두 좌석은 「어느 것」에서 못 갈라지고
    「언제」에서만 갈라집니다."""
    probes = []
    _document(monkeypatch, [_join("a678_ok")], probes=probes)

    synthesis.approval_report(None, known_tables=TABLES)
    synthesis.approval_report(None, known_tables=TABLES)

    assert len(probes) == 2, "두 번째 새로고침이 «옛 답»을 냈습니다"
    assert synthesis._RIGHT_KEYS["loaded"] is False, (
        "보고서가 쓰기 경로의 캐시를 «채웠습니다» — 그러면 다음 배치가 이 요청의 답을 씁니다")


# ⚰️ [판정 652 3걸음, 예고대로] `test_the_response_has_the_same_cells_the_retiring_route_had`
#    가 여기 있었습니다. 그 줄의 독스트링이 수명을 스스로 적어 뒀습니다 — 「옛 라우트가
#    걷히는 커밋에서 «같이» 죽는다. 그때는 비교할 반쪽이 없고, 그 시점에는 클라가 이미 새
#    자리를 부르고 있다」. 둘 다 참이 됐습니다(클라는 `31a62dcb`·`4f9c8779`).


def test_the_route_stands_at_its_new_name_and_the_old_one_is_still_there():
    """⚠️ 「돈다」로 잽니다 — 앱이 실제로 그 경로를 들고 있는지. 그리고 옛 자리가 «없다»는
    것도 같이 잽니다: 678 ③ 은 라우트와 문법이 «한 커밋»에 가는 것이고, 라우트만 남으면
    그것이 지울 로더 위에서 도는 반쪽 상태입니다."""
    import main

    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    assert "/admin/chain/join/verify" in paths
    # ⚰️ [652 3걸음] 옛 라우트가 «아직 산다»를 여기서 단언했습니다. 클라가 옮겼고(678 ②)
    #    이 커밋이 라우트와 문법을 «같이» 걷었습니다 — 이제 없는 것이 계약입니다.
    assert "/admin/config/virtual-join/verify" not in paths
