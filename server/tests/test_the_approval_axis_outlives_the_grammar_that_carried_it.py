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
# ⓒ 거절 — 갈래를 가려서 싣는다
# ---------------------------------------------------------------------------

def test_a_refused_join_declaration_lands_in_invalid(monkeypatch):
    bad = _join("a678_refused")
    bad["into"] = {"read": True}                       # 읽기 시점 조인 = 은퇴한 능력
    _document(monkeypatch, [bad])

    report = synthesis.approval_report(None, known_tables=TABLES)

    assert [item["subject"] for item in report["invalid"]] == ["a678_refused"]
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


def test_the_response_has_the_same_cells_the_retiring_route_had(tmp_path):
    """🔴 [판정 678] 응답 «모양»이 같아야 클라 변경이 URL 한 줄입니다. 옛 라우트를 «실제로»
    돌려 그 행의 칸을 받아 견줍니다 — 제가 타이핑한 목록과 견주면 그 목록이 답을 정합니다.

    ⚰️ 이 줄은 옛 라우트가 걷히는 커밋에서 «같이» 죽습니다 (652 3걸음). 그때는 비교할
    반쪽이 없고, 그 시점에는 클라가 이미 새 자리를 부르고 있습니다.
    """
    from tests.test_virtual_join_guard import FakeDB, TABLES as OLD_TABLES, _decl
    from chain import legacy_join_declaration as old

    path = tmp_path / "vj.json"
    path.write_text(json.dumps({
        "ok": _decl("vjoin_log", "vjoin_wafer_map",
                    [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
    }), encoding="utf-8")
    old_report = old.verification_report(
        FakeDB({"vjoin_wafer_map":
                {"uq_vjoin_vjoin_wafer_map_lot_slot_ns": ["lot", "slot"]}}),
        path=str(path), known_tables=OLD_TABLES)
    assert old_report["declarations"], "옛 보고서가 행을 안 냈습니다 — 비교가 공허합니다"

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as patch:
        _document(patch, [_join("a678_ok")])
        new_report = synthesis.approval_report(None, known_tables=TABLES)

    assert set(new_report) == set(old_report)
    assert set(new_report["declarations"][0]) == set(old_report["declarations"][0])


def test_the_route_stands_at_its_new_name_and_the_old_one_is_still_there():
    """⚠️ 「돈다」로 잽니다 — 앱이 실제로 두 경로를 들고 있는지. 옛 것이 «아직 사는» 것이
    이 걸음의 계약입니다 (판정 672·678: 먼저 지우면 그 사이가 거짓)."""
    import main

    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    assert "/admin/chain/join/verify" in paths
    assert "/admin/config/virtual-join/verify" in paths
