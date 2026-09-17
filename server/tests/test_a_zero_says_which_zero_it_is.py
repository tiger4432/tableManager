# -*- coding: utf-8 -*-
"""S-284. «0» 이 무엇의 0 인지 말한다 — 그리고 「못 읽음」은 0 이 «아니다».

🔴 세 상태가 오늘 «같은 픽셀»입니다:
```
진짜 0    파일을 읽었고 선언이 없다          -> 0 이 맞고, 그것도 정보다
못 읽음    파일/로더가 터졌다                 -> 0 이 «아니다». 수를 내면 안 된다
거절됨    선언은 있는데 제품이 거부했다        -> 0 이 아니다. 「선언이 없다」와 정반대다
```
운영자에게 셋의 «행동»이 다릅니다 — 아무것도 안 함 · 고장을 고침 · 선언을 고침. 한 픽셀로
내보내면 셋 중 둘이 첫째로 읽힙니다.

⚠️ 축이 «둘»이고 섞으면 안 됩니다(S-284 ③): `absence` 는 「0 이 무엇의 0 인가」,
`unread` 는 「수를 아예 안 그린다」. 그래서 못 읽은 자리는 «칸이 아예 없어야» 하고
(판정 445 ④), 0 을 적는 것이 아닙니다.

📎 계측한 모집단: A(어떤 0 인지 안 말하는 칸) 142 — 라우트 안 24 · 헬퍼 118,
   B(삼킨 실패가 수가 되는 자리) 9. 이 파일은 B 부터 덮습니다.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain.graph                                                    # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402

TRIGGER, TARGET, DERIVED, RIGHT = ("z_trigger", "z_target", "z_derived", "z_reference")


class _FakeDb:
    def get_bind(self):
        return type("B", (), {"dialect": type("D", (), {"name": "sqlite"})()})()


def _graph(monkeypatch, loader):
    # ⚠️ NOT `enrichment` — that is the MODULE's name two lines down, and a parameter
    #    spelled the same shadows it, so the patch lands on the loader's `.config`
    #    attribute instead of the module's. Measured, not foreseen.
    """The assembler, with only the enrichment loader varied.

    🔴 ONE AXIS AT A TIME. Every other quarter answers the same way in all three cases, so a
    difference in the output can only have come from the loader that was varied.
    """
    from chain import enrichment
    from chain import legacy_join_declaration as vjc
    from database import crud

    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    monkeypatch.setattr(enrichment.config, "load_enrichment_rules", loader)
    monkeypatch.setattr(vjc, "load_virtual_join_rules", lambda **kw: [])
    monkeypatch.setattr(crud, "TABLE_CONFIG", {TRIGGER: {}, TARGET: {}})
    monkeypatch.setattr("ledger.setup.load_setup",
                        lambda *a, **kw: type("Setup", (), {
                            "snapshot": type("S", (), {"source_plans": {}})()})())
    return chain.graph.chain_graph(_FakeDb())


# ---------------------------------------------------------------------------
# chain/graph.py — the seat 판정 S-284 ① named
# ---------------------------------------------------------------------------

def test_a_file_that_declared_nothing_counts_zero(monkeypatch):
    """진짜 0. 읽었고, 없었다 — 그 0 은 답이고 «칸이 있어야» 한다."""
    graph = _graph(monkeypatch, lambda **kw: [])

    assert graph["counts"]["enrichment_rules"] == 0
    assert "enrichment_rules" not in graph.get("unread", {})


def test_a_loader_that_raised_publishes_no_number_at_all(monkeypatch):
    """🔴 못 읽음은 0 이 «아니다». 칸이 아예 없고, 왜인지가 다른 자리에 선다.

    떨어뜨리면 화면의 머리 줄에서 그 이름이 «사라집니다» — 그것이 「말 안 함」의 철자이고,
    `countLine` 이 응답이 준 키만 그리므로 클라는 한 글자도 안 바뀝니다.
    """
    def _boom(**kw):
        raise RuntimeError("enrichment_rules.json: unterminated string")

    graph = _graph(monkeypatch, _boom)

    assert "enrichment_rules" not in graph["counts"], (
        "못 읽었는데 수가 나갔습니다 — 「선언 0」과 같은 픽셀입니다")
    assert "enrichment_rules" in graph["unread"]
    assert "unterminated string" in graph["unread"]["enrichment_rules"], (
        "사유가 없으면 운영자가 어느 파일을 여는지 모릅니다")


def test_a_declaration_the_product_refused_is_not_the_same_as_none(monkeypatch):
    """거절됨. 「선언이 없다」와 «정반대»다 — 선언은 있고, 제품이 안 받았다."""
    def _refuses(**kw):
        rej = kw.get("rejections")
        if rej is not None:
            rej.append({"scope": "rule", "subject": "z_rule", "detail": "no decision_key"})
        return []

    graph = _graph(monkeypatch, _refuses)

    assert graph["counts"]["enrichment_rules"] == 0
    assert graph["counts"]["enrichment_rules_refused"] == 1, (
        "거절이 «0 선언»으로 접혔습니다 — 운영자는 파일을 고쳐야 하는데 할 일이 없다고 읽습니다")


def test_the_refused_key_is_absent_when_nothing_was_refused(monkeypatch):
    """⛔ 0 을 적지 않는다. 「거절 0」은 «줄이 없는 것»으로 말해진다 — 이 파일의 `contested`
    가 이미 그 규율이고, 항상 켜진 0 은 머리 줄을 길게만 만든다."""
    graph = _graph(monkeypatch, lambda **kw: [])

    assert "enrichment_rules_refused" not in graph["counts"]


def test_the_three_states_are_three_different_answers(monkeypatch):
    """🔴 이 파일의 «판별식». 셋을 나란히 놓고 «서로 다른지»를 본다 — 하나씩 보면
    각각은 언제나 그럴듯하고, 둘이 같아진 순간은 나란히 놓을 때만 보인다."""
    def _refuses(**kw):
        rej = kw.get("rejections")
        if rej is not None:
            rej.append({"subject": "z_rule", "detail": "no decision_key"})
        return []

    def _boom(**kw):
        raise RuntimeError("x")

    answers = []
    for loader in (lambda **kw: [], _boom, _refuses):
        with monkeypatch.context() as m:
            g = _graph(m, loader)
            answers.append((g["counts"].get("enrichment_rules"),
                            g["counts"].get("enrichment_rules_refused"),
                            "enrichment_rules" in g.get("unread", {})))

    assert len(set(answers)) == 3, answers


# ---------------------------------------------------------------------------
# chain_bindings.identity_column — 「선언이 없다」와 「제품이 거절했다」
# ---------------------------------------------------------------------------

def _identity(monkeypatch, cols_or_raise, config):
    import chain_bindings
    import dt_map_derivation

    def _cols(table):
        if isinstance(cols_or_raise, Exception):
            raise cols_or_raise
        return cols_or_raise

    monkeypatch.setattr(dt_map_derivation, "identity_columns", _cols)
    monkeypatch.setattr(chain_bindings, "_table_config", lambda t: config)
    return chain_bindings.identity_column("z_table")


def test_a_table_that_declares_nothing_says_exactly_that(monkeypatch):
    """진짜 없음. 선언이 없고, 문장이 그렇게 말한다 — 오늘도 맞다."""
    name, why = _identity(monkeypatch, [], {})

    assert name is None
    assert "declares neither" in why


def test_a_refused_derivation_does_not_read_as_an_absent_declaration(monkeypatch):
    """🔴 거절은 부재의 «반대»다. 선언이 있고, 제품이 안 받았다.

    오늘 이 자리는 `except DerivationRefused: cols = []` 로 떨어져서 운영자에게
    「map_key_columns 를 적으십시오」라고 말한다 — 그가 «이미 적어 둔» 것을. 그러면 그는
    적힌 것을 다시 적으러 가고, 진짜 사유(제품이 왜 거절했나)는 어디에도 안 뜬다.
    """
    import dt_map_derivation
    refusal = dt_map_derivation.DerivationRefused(
        "scope_too_large", "map_key_columns spans 3 tables")

    name, why = _identity(monkeypatch, refusal, {})

    assert name is None
    assert "scope_too_large" in why, (
        "거절 코드가 사라졌습니다 — 운영자가 어느 규칙을 고쳐야 하는지 모릅니다: %s" % why)
    assert "declares neither" not in why, (
        "거절이 «선언 없음»의 문장을 입었습니다 — 정반대를 말하고 있습니다")


def test_a_refusal_does_not_stop_the_business_key_from_answering(monkeypatch):
    """⚠️ 통제. 거절은 «첫째 전략»만 막는다 — 둘째가 답할 수 있으면 답한다.

    이 줄이 없으면 위 수리가 「거절이면 무조건 거절」로 번져서, 오늘 도는 표가 멈춘다.
    """
    import dt_map_derivation
    refusal = dt_map_derivation.DerivationRefused("scope_too_large", "x")

    name, origin = _identity(monkeypatch, refusal,
                             {"business_key": "job", "column_types": {"job": "string"}})

    assert name == "job", origin


# ---------------------------------------------------------------------------
# map_alignment._no_cell_refusal — 넷째 원인이 첫째의 문장을 입고 나간다
# ---------------------------------------------------------------------------

def _no_cells(monkeypatch, binding, rows=0):
    import map_alignment

    def _binding_of(cfg, table):
        if isinstance(binding, Exception):
            raise binding
        return binding

    monkeypatch.setattr(map_alignment, "_binding_of", _binding_of)
    monkeypatch.setattr(map_alignment.map_overlay, "map_key_parts",
                        lambda b, m: [("job", m)])
    return map_alignment._no_cell_refusal(None, {}, "z_map", "M1", known_count=rows)


def test_a_key_with_no_rows_says_it_has_no_coordinates(monkeypatch):
    """ⓐ 진짜 없음. 이 함수의 독스트링이 세 원인을 «스스로» 적어 두었고, 이것이 첫째다."""
    import map_alignment
    code, text = _no_cells(monkeypatch, {"key_columns": ["job"]})

    assert code == map_alignment.REF_REFUSAL_NO_CELLS
    assert "좌표가 없습니다" in text


def test_an_unreadable_binding_is_not_reported_as_an_empty_key(monkeypatch):
    """🔴 넷째 원인 — 그리고 오늘 그것은 첫째의 «문장을 입고» 나간다.

    `except ValueError: key_cols = []` 뒤로는 `bound` 도 None 이라 「조회 조건」이 문장에서
    «사라진다» — 그런데 이 함수의 독스트링이 바로 그 조회 조건을 「ⓒ를 자명하게 만드는 것」
    이라고 적어 두었다. 즉 못 읽은 경우에만, 진단의 열쇠가 조용히 빠진 채 「셀이 없습니다」가 나간다.

    ⚠️ 낱말을 지어내지 «않는다». `REF_REFUSAL_BINDING`("binding_unresolved")이 이미 이
    뜻으로 선언돼 있고 이 자리가 그것을 안 쓰고 있었다 — 어휘가 있는데 지나는 사람이 없는
    S-284 ②의 모양 그대로다.
    """
    import map_alignment
    code, text = _no_cells(monkeypatch,
                           ValueError("맵 테이블 'z_map'에 map_key_columns 선언이 없습니다"))

    assert code == map_alignment.REF_REFUSAL_BINDING, (
        "바인딩을 못 읽은 것이 「셀이 없다」로 나갔습니다: %s" % code)
    assert "map_key_columns" in text, text


def test_the_two_causes_do_not_share_a_sentence(monkeypatch):
    """판별식 — 나란히 놓고 «다른지»를 본다."""
    a = _no_cells(monkeypatch, {"key_columns": ["job"]})
    b = _no_cells(monkeypatch, ValueError("x"))

    assert a[0] != b[0] and a[1] != b[1], (a, b)


# ---------------------------------------------------------------------------
# chain/ingestion_worker — 🔎 계측기가 «틀렸고», 그 자리는 이미 옳았다
# ---------------------------------------------------------------------------
# 계측기가 `run_ledger_row_census` 의 `len(sources)` 두 줄을 B 로 찍었습니다. 아니었습니다 —
# 그 블록 전체가 `if sources:` 안이라, 못 읽어서 `sources` 가 비면 «랩 자체가 안 발행됩니다».
# 그것이 「말 안 함」의 가장 강한 철자이고(칸이 아니라 «항목»이 없습니다), 위의 WARNING 하나만
# 나갑니다. 제가 여기에 `depth=None if unread else ...` 를 넣었다가 «무릅니다» — `unread` 가
# 참인 경우는 그 블록에 «도달할 수 없어서» 죽은 가지였습니다.
#
# 🔴 남기는 것은 «사실»입니다: 계측기의 B 는 「except 가 비운 이름이 세어진다」를 재지
#    「그 줄에 도달하는가」를 안 잽니다. 목록을 «열어 보지» 않았으면 죽은 가지를 착지시킬
#    뻔했습니다 (실제로 한 번 넣었다가 뺐습니다).
#
# ⚰️ [해소됨 2026-09-17] 여기 「`heartbeat.record_lap` 의 그 성질은 시험이 «없습니다»」라고
#    적어 두었는데, 그 말이 «반만 맞았습니다». 열어 보니 이웃이 절반을 «이미» 재고 있었습니다:
#      ✅ 「아예 보고 안 함 -> 키 없음」   test_a_loop_that_never_reported_has_no_lap_keys
#      ✅ 「depth=7 -> 7 로 나옴」        test_a_recorded_lap_reaches_the_route_with_its_own_numbers
#      🔴 「depth=0 -> «0 으로 남는다»」  <- 이 절반이 «진짜로» 비어 있었습니다
#    그 절반이 이 축의 «핵심»입니다: `if depth is not None` 을 `if depth` 로 바꾸면
#    「큐가 비었다(0)」가 「아무 말도 안 했다」로 조용히 바뀌는데, 그러고도 «28 시험이 초록»이었습니다.
#    -> 변이로 재서 구멍을 «확인한 뒤» 채웠습니다:
#       test_the_nine_loops_say_what_they_last_did.py::test_a_real_zero_survives_...
#       (그리고 `**extra` 도 같은 규칙이라 같이 — 인자 이름으로 문이 갈리면 안 됩니다)
# 🔴 교훈은 「시험이 없다」를 적기 «전»에 이웃을 열라는 것입니다. 없다고 적은 자리가 반은 있었고,
#    정작 «비어 있던 절반»은 제가 적은 문장과 다른 것이었습니다.

# ---------------------------------------------------------------------------
# main.get_ingestion_workspaces — 🔎 서버는 «이미» 가른다. 화면이 안 읽는다
# ---------------------------------------------------------------------------
# 🔴 A 축(142 중 라우트 안 24)을 자리마다 물었습니다. 판별식은 「낱말이 있나」가 아니라
#    «이 0 이 두 뜻일 수 있나, 그리고 서버가 가를 수 있나»입니다. 스물넷 «전부» 가릅니다 —
#    형제 칸(`truncated` · `capped` · `declarations` · `oldest_failed_at` · `raws_dir`)이거나,
#    못 읽으면 404/503 으로 «거절»하거나, 그 0 이 「이 동작이 아무것도 안 했다」 한 뜻뿐입니다.
#
# ⚰️ 저는 이 자리를 «서버 결함으로 읽고 고치려 했습니다». 열어 보니 바로 옆 줄이
#    `raws_dir: raws_dir if os.path.exists(raws_dir) else None` 이었습니다 — 서버는 말하고
#    있었고, 제가 그 칸을 «안 보고» 수리를 설계했습니다. 계측기가 `absence`/`unread` 라는
#    «제가 아는 두 낱말»만 형제로 인정한 탓이고, 이 저장소의 부재 어휘는 자리마다 다릅니다.
#
# 🔴 그래서 이 자리의 병은 «클라 레인»입니다 — `admin_rows.js` 가 `raw_files_count > 0` 이
#    아니면 «초록 0» 배지를 그립니다(「받은 파일 없음, 이상 없음」). raws 디렉터리가 «없을 때»도
#    같은 초록 0 입니다. 운영자는 파일을 거기 떨어뜨리고 초록을 보며 「한가하다」고 읽는데,
#    사실 그 파일은 «아무도 안 보는 자리»에 있습니다. `raws_dir` 이 null 이면 그렇게 그리면 안 됩니다.
#
# 아래 둘은 «그 클라 수리가 기댈 서버의 사실»을 못 박습니다. 서버 쪽 변경은 «없습니다».

def test_the_payload_already_tells_an_empty_inbox_from_a_missing_one(tmp_path, monkeypatch):
    """서버가 가른다 — 있으면 경로, 없으면 null. 이 줄이 클라 수리의 «재료»다."""
    import main
    (tmp_path / "wsA" / "raws").mkdir(parents=True)
    (tmp_path / "wsB").mkdir()
    monkeypatch.setattr(main.paths, "WORKSPACE_DIR", str(tmp_path))

    rows = {r["name"]: r for r in main.get_ingestion_workspaces()["data"]}

    assert rows["wsA"]["raws_dir"] is not None, "받을 자리가 있는데 null 입니다"
    assert rows["wsB"]["raws_dir"] is None, (
        "받을 자리가 없는데 경로가 나갔습니다 — 그러면 클라가 가를 재료를 잃습니다")


def test_the_count_alone_cannot_tell_them_apart(tmp_path, monkeypatch):
    """🔴 그리고 «수만 보면» 둘이 같다 — 화면이 오늘 그 수만 봅니다.

    이 단언이 이 파일에 있는 이유는 「서버는 이미 옳다」를 못 박으려는 것이 아니라, 클라가
    수 «하나»로 판단하는 한 그 화면은 «구조적으로» 두 사실을 못 가른다는 것을 값으로 남기려는
    것입니다. 클라가 `raws_dir` 을 읽는 날 이 줄은 그대로 참이고, 그때 그림만 달라집니다.
    """
    import main
    (tmp_path / "wsA" / "raws").mkdir(parents=True)
    (tmp_path / "wsB").mkdir()
    monkeypatch.setattr(main.paths, "WORKSPACE_DIR", str(tmp_path))

    rows = {r["name"]: r for r in main.get_ingestion_workspaces()["data"]}

    assert rows["wsA"]["raw_files_count"] == rows["wsB"]["raw_files_count"] == 0, (
        "수가 갈렸다면 이 관찰이 낡은 것입니다 — 그러면 클라 항목을 다시 재십시오")