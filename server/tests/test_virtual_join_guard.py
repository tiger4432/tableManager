"""VIRTUAL JOIN 팬아웃 가드 ― 선언이 터지기 전에 거부되는가.

무엇을 지키는가 (사용자 2026-07-31: *"당연히 조인키는 안터지게 config로 잘 정해놓지.
터지는 config는 인식 안되게 가드 만들어."*)
    조인 키가 오른쪽 행 하나를 지목하지 못하는 선언은 **유효 규칙 목록에 들어가지
    않는다.** 문법도 맞고 컬럼도 존재하는 선언이므로 이 검사가 없으면 거부할 자리가 없다.

이 파일의 기준선은 상상이 아니라 **실측**이다 (운영 DB read-only, 2026-07-31):
    core_defect_map ⋈ eds_fail_map (lot,slot,x,y)   103,040 →     103,040   x1
    core_defect_map ⋈ eds_fail_map (lot,slot)       103,040 → 132,715,520   x1288
    bonding_log     ⋈ wafer_process (lot,slot)       14,436 →   2,552,624   x177
    bonding_log     ⋈ core_wafer_map (core_lot,core_slot) 14,436 → 14,436   x1
세 케이스의 table_config 모양을 그대로 재현해, 가드가 x1을 통과시키고 x1288/x177을
거부하는지 채점한다. 조합 수가 아니라 **결함 축을 실제로 활성화하는 픽스처**가 회귀
강도를 만든다(server-pm 교훈).

테이블명 규약: 사용자 config(gitignored)에 실존할 수 없는 `vjoin_` 접두를 쓴다 ―
겹치면 import 시점 `init_dynamic_models`가 공유 sqlite에 실 스키마를 선점한다.
"""
import json
import os
import sys

import pytest

_SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import config_resolve_report as crr          # noqa: E402
import virtual_join_config as vjc            # noqa: E402


# ---------------------------------------------------------------------------
# 실측 3종을 재현하는 table_config
# ---------------------------------------------------------------------------

# 컬럼 집합은 운영 table_config 그대로다 ― `metro_eqp`는 eds_fail_map 에만 있고
# core_defect_map 에는 없다. 양쪽에 다 넣으면 shadow 가드가 먼저 걸려 팬아웃 가드가
# 한 번도 실행되지 않는다(그 상태로 통과하는 테스트는 아무것도 증명하지 않는다).
MAP_COLS = {"lot": "string", "slot": "string", "x": "number", "y": "number",
            "val": "string", "chip_key": "string"}

TABLES = {
    # 왼쪽: 칩 단위 맵 (core_defect_map 모양)
    "vjoin_defect_map": {
        "business_key": "chip_key",
        "composite_key_source": ["lot", "slot", "x", "y"],
        "column_types": dict(MAP_COLS),
    },
    # 오른쪽: 같은 모양의 맵. 행 정체성이 lot+slot+x+y 다 (eds_fail_map 모양)
    "vjoin_fail_map": {
        "business_key": "chip_key",
        "composite_key_source": ["lot", "slot", "x", "y"],
        "column_types": dict(MAP_COLS, metro_eqp="string"),
    },
    # 오른쪽: 행 정체성이 lot+slot 뿐인 파생 테이블 (core_wafer_map 모양)
    "vjoin_wafer_map": {
        "business_key": "core_key",
        "composite_key_source": ["lot", "slot"],
        "column_types": {"core_key": "string", "lot": "string", "slot": "string",
                         "wafer_id": "string", "chip_count": "number"},
    },
    # 오른쪽: 단일 business_key 이고 그 키가 조인 키에 없다 (wafer_process 모양)
    "vjoin_process": {
        "business_key": "proc_id",
        "column_types": {"proc_id": "string", "lot": "string", "slot": "string",
                         "eqp_id": "string", "result": "string"},
    },
    # 오른쪽: 행 정체성 선언이 아예 없다
    "vjoin_keyless": {
        "column_types": {"lot": "string", "slot": "string", "note": "string"},
    },
    # 왼쪽: 로그성 테이블 (bonding_log 모양)
    "vjoin_log": {
        "business_key": "log_id",
        "column_types": {"log_id": "string", "lot": "string", "slot": "string",
                         "eqp_id": "string", "bx": "number"},
    },
}


def _decl(left, right, pairs, expose, **extra):
    d = {"left_table": left, "right_table": right,
         "join_key": [{"left": a, "right": b} for a, b in pairs],
         "expose": list(expose)}
    d.update(extra)
    return d


def _load(decls, tables=None):
    """선언 dict -> (통과 규칙 목록, 거부 목록). 파일 경로를 타지 않는 순수 검증 경로."""
    rejections = []
    rules = vjc.validate_virtual_join_rules(
        decls, known_tables=TABLES if tables is None else tables,
        rejections=rejections)
    return rules, rejections


def _codes(rejections):
    return [r.get("code") for r in rejections]


# ---------------------------------------------------------------------------
# 가드 본체 ― 실측 3종
# ---------------------------------------------------------------------------

def test_chip_identity_join_is_accepted():
    """x1 로 측정된 선언은 통과해야 한다. 가드가 전부 거부하면 이 테스트가 잡는다."""
    rules, rej = _load({"chip": _decl("vjoin_defect_map", "vjoin_fail_map",
                                      [("lot", "lot"), ("slot", "slot"),
                                       ("x", "x"), ("y", "y")],
                                      ["metro_eqp"])})
    assert rej == [], f"clean declaration was rejected: {rej}"
    assert [r["name"] for r in rules] == ["chip"]
    assert rules[0]["right_columns"] == ["lot", "slot", "x", "y"]
    assert rules[0]["declared_key"] == ["lot", "slot", "x", "y"]
    # 정적 통과를 유일성의 증거로 읽지 못하게 등급은 여전히 미검증이다.
    assert rules[0]["uniqueness_evidence"] == vjc.EVIDENCE_UNVERIFIED


def test_map_identity_join_is_refused_the_1288x_case():
    """실측 x1288. 오른쪽 정체성 lot+slot+x+y 중 x,y 를 조인 키가 고정하지 못한다."""
    rules, rej = _load({"mapwide": _decl("vjoin_defect_map", "vjoin_fail_map",
                                         [("lot", "lot"), ("slot", "slot")],
                                         ["metro_eqp"])})
    assert rules == [], "a 1288x fan-out declaration was admitted"
    assert _codes(rej) == [vjc.CODE_KEY_NOT_COVERED]
    # 운영자가 무엇을 고쳐야 하는지 사유가 지목해야 한다.
    assert "x" in rej[0]["detail"] and "y" in rej[0]["detail"]


def test_business_key_not_in_join_key_is_refused_the_177x_case():
    """실측 x177. 오른쪽은 proc_id 로 행을 지목하는데 조인 키에 proc_id 가 없다."""
    rules, rej = _load({"proc": _decl("vjoin_log", "vjoin_process",
                                      [("lot", "lot"), ("slot", "slot")],
                                      ["result"])})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_KEY_NOT_COVERED]
    assert "proc_id" in rej[0]["detail"]


def test_derived_table_join_is_accepted_the_flagship():
    """실측 x1. 파생 테이블의 정체성이 곧 조인 키인 경우 ― 이 기능의 주 용도다."""
    rules, rej = _load({"wafer": _decl("vjoin_log", "vjoin_wafer_map",
                                       [("lot", "lot"), ("slot", "slot")],
                                       ["wafer_id"])})
    assert rej == []
    assert rules[0]["expose"] == ["wafer_id"]


def test_right_table_with_no_declared_key_is_refused():
    """정체성 선언이 없는 테이블은 **어떤** 조인 키로도 행 하나를 주장할 수 없다."""
    rules, rej = _load({"keyless": _decl("vjoin_log", "vjoin_keyless",
                                         [("lot", "lot"), ("slot", "slot")],
                                         ["note"])})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_KEY_NOT_COVERED]


def test_duplicate_right_binding_cannot_widen_the_key():
    """같은 오른쪽 컬럼을 두 번 묶어 덮임 판정을 통과시키는 우회를 막는다."""
    rules, rej = _load({"dup": _decl("vjoin_defect_map", "vjoin_fail_map",
                                     [("lot", "lot"), ("slot", "slot"),
                                      ("x", "lot"), ("y", "lot")],
                                     ["metro_eqp"])})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_SHAPE]


def test_aggregate_form_is_a_named_refusal_not_an_escape_hatch():
    """유일성 검사를 끄는 스위치는 그것이 향할 안전한 경로가 생긴 뒤에 열린다."""
    rules, rej = _load({"agg": _decl("vjoin_defect_map", "vjoin_fail_map",
                                     [("lot", "lot"), ("slot", "slot")],
                                     ["metro_eqp"], join_cardinality="many")})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_FANOUT_DECLARED]


# ---------------------------------------------------------------------------
# 모양 검증
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("decl,why", [
    (_decl("nope_table", "vjoin_wafer_map", [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
     "unknown left table"),
    (_decl("vjoin_log", "nope_table", [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
     "unknown right table"),
    (_decl("vjoin_log", "vjoin_wafer_map", [("nope", "lot"), ("slot", "slot")], ["wafer_id"]),
     "left join column missing"),
    (_decl("vjoin_log", "vjoin_wafer_map", [("lot", "nope"), ("slot", "slot")], ["wafer_id"]),
     "right join column missing"),
    (_decl("vjoin_log", "vjoin_wafer_map", [("lot", "lot"), ("slot", "slot")], ["nope"]),
     "expose column missing"),
    (_decl("vjoin_log", "vjoin_wafer_map", [("lot", "lot"), ("slot", "slot")], ["wafer_id", "wafer_id"]),
     "duplicate expose"),
    (_decl("vjoin_log", "vjoin_wafer_map", [], ["wafer_id"]),
     "empty join key"),
    (_decl("vjoin_log", "vjoin_wafer_map", [("lot", "lot"), ("slot", "slot")], []),
     "empty expose"),
])
def test_shape_errors_are_rejected(decl, why):
    rules, rej = _load({"r": decl})
    assert rules == [], f"{why}: declaration was admitted"
    assert len(rej) == 1 and rej[0]["code"] == vjc.CODE_SHAPE, why


def test_expose_cannot_shadow_a_left_column():
    """왼쪽에 같은 이름이 있으면 어느 쪽 값을 보고 있는지 알 수 없는 표가 된다."""
    rules, rej = _load({"shadow": _decl("vjoin_log", "vjoin_wafer_map",
                                        [("lot", "lot"), ("slot", "slot")],
                                        ["slot"])})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_SHAPE]
    assert "slot" in rej[0]["detail"]


def test_sql_identifier_shape_is_enforced_before_anything_runs():
    """이름이 프로브 경로에 닿기 전에 형태를 강제한다."""
    for bad in ['lot" OR "1"="1', "lot;drop", "1lot", ""]:
        rules, rej = _load({"inj": _decl("vjoin_log", "vjoin_wafer_map",
                                         [(bad, "lot"), ("slot", "slot")], ["wafer_id"])})
        assert rules == [], f"{bad!r} was admitted as a column name"


def test_disabled_declaration_is_skipped_without_a_rejection():
    rules, rej = _load({"off": _decl("vjoin_defect_map", "vjoin_fail_map",
                                     [("lot", "lot")], ["metro_eqp"], enabled=False)})
    assert rules == [] and rej == [], "disabled is not an error"


def test_underscore_keys_are_comments_not_declarations():
    rules, rej = _load({"_comment": "not a declaration",
                        "ok": _decl("vjoin_log", "vjoin_wafer_map",
                                    [("lot", "lot"), ("slot", "slot")], ["wafer_id"])})
    assert [r["name"] for r in rules] == ["ok"] and rej == []


def test_unresolved_label_defaults_and_covers_empty_values():
    """미상은 「오른쪽 행 없음」과 「값이 빔」을 모두 덮는다 ― 기본값이 선언에 실린다."""
    rules, _ = _load({"r": _decl("vjoin_log", "vjoin_wafer_map",
                                 [("lot", "lot"), ("slot", "slot")], ["wafer_id"])})
    assert rules[0]["unresolved_label"] == vjc.DEFAULT_UNRESOLVED_LABEL == "미상"
    doc = vjc.__doc__
    assert "값이 비어" in doc and "no right row" in doc, (
        "the module contract must state that 미상 covers matched-but-NULL too - "
        "26.27% of bonding_log rows are exactly that case")


# ---------------------------------------------------------------------------
# 파일 경로
# ---------------------------------------------------------------------------

def test_missing_file_is_not_a_rejection(tmp_path):
    """부재는 거부가 아니다(선언이 없을 뿐) ― INV-F9-6과 같은 규율."""
    rej = []
    rules = vjc.load_virtual_join_rules(path=str(tmp_path / "absent.json"),
                                        known_tables=TABLES, rejections=rej)
    assert rules == [] and rej == []


def test_unreadable_file_is_a_file_scoped_rejection(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{ not json", encoding="utf-8")
    rej = []
    rules = vjc.load_virtual_join_rules(path=str(p), known_tables=TABLES, rejections=rej)
    assert rules == []
    assert len(rej) == 1 and rej[0]["scope"] == "file"


def test_non_object_root_is_rejected(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[]", encoding="utf-8")
    rej = []
    assert vjc.load_virtual_join_rules(path=str(p), known_tables=TABLES,
                                       rejections=rej) == []
    assert rej and rej[0]["scope"] == "file"


def test_the_shipped_sample_parses_and_its_example_is_the_measured_shape():
    """샘플이 실제로 로드되는지, 그리고 거부 예시가 실측 x1288 모양인지."""
    sample = os.path.join(_SERVER, "config", "virtual_join_rules.json.sample")
    raw = json.loads(open(sample, encoding="utf-8").read())
    ex = raw["_example_rejected_map_identity_join"]
    assert ex["left_table"] == "core_defect_map" and ex["right_table"] == "eds_fail_map"
    assert [p["right"] for p in ex["join_key"]] == ["lot", "slot"]


# ---------------------------------------------------------------------------
# 라이브 유일성 (②) ― 부분집합 논리와 등급
# ---------------------------------------------------------------------------

def test_unique_index_subset_logic():
    """`(a)`에 UNIQUE가 있으면 `(a,b)`로도 유일하다 ― 부분집합이면 충분하다."""
    class FakeDB:
        def __init__(self, rows):
            self._rows = rows

        def get_bind(self):
            class B:
                class dialect:
                    name = "postgresql"
            return B()

        def execute(self, *a, **k):
            rows = self._rows

            class R:
                def fetchall(self_inner):
                    return rows
            return R()

    assert vjc.unique_index_covering(FakeDB([("uq_a", ["a"])]), "t", ["a", "b"]) == "uq_a"
    assert vjc.unique_index_covering(FakeDB([("uq_ab", ["a", "b"])]), "t", ["a", "b"]) == "uq_ab"
    # 조인 키가 못 덮는 인덱스는 근거가 못 된다.
    assert vjc.unique_index_covering(FakeDB([("uq_c", ["c"])]), "t", ["a", "b"]) is None


def test_non_postgres_gets_no_permanent_guarantee():
    """모르는 것은 모른다고 한다 ― 안전한 방향의 무지."""
    class FakeDB:
        def get_bind(self):
            class B:
                class dialect:
                    name = "sqlite"
            return B()

        def execute(self, *a, **k):
            raise AssertionError("must not query a non-postgres catalog")

    assert vjc.unique_index_covering(FakeDB(), "t", ["a"]) is None


@pytest.mark.parametrize("probe_status,expect_refused,expect_code", [
    ("clean", False, None),
    ("duplicate", True, vjc.CODE_DUPLICATE_FOUND),
    ("incomplete", True, vjc.CODE_PROBE_INCOMPLETE),
])
def test_probe_incomplete_is_not_clean(monkeypatch, probe_status, expect_refused, expect_code):
    """증명하지 못한 것을 통과시키면 이 가드가 존재하는 이유가 사라진다."""
    monkeypatch.setattr(vjc, "unique_index_covering", lambda *a, **k: None)
    monkeypatch.setattr(vjc, "probe_duplicate",
                        lambda *a, **k: {"status": probe_status, "sample": None})
    rule = {"right_table": "t", "right_columns": ["a"]}
    out = vjc.verify_uniqueness(object(), rule)
    assert out["refused"] is expect_refused
    assert out["code"] == expect_code


def test_load_verified_rules_drops_what_the_live_check_refuses(tmp_path, monkeypatch):
    """①+② 둘 다 통과한 것만 나오는 진입점. 조인을 실행할 코드가 써야 하는 함수다.

    실측이 이 함수의 존재 이유다: `bonding_map`은 선언 키 `base+x+y`로 ①을 **통과**하지만
    실제 중복 그룹이 2,312개다. ①만 소비하면 그 선언이 살아서 나간다.
    """
    p = tmp_path / "vj.json"
    p.write_text(json.dumps({
        "good": _decl("vjoin_log", "vjoin_wafer_map",
                      [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
        "dirty": _decl("vjoin_defect_map", "vjoin_fail_map",
                       [("lot", "lot"), ("slot", "slot"), ("x", "x"), ("y", "y")],
                       ["metro_eqp"]),
    }), encoding="utf-8")

    def fake_verify(db, rule, budget_ms=None):
        if rule["right_table"] == "vjoin_fail_map":      # ①은 통과, ②에서 중복 발견
            return {"uniqueness_evidence": vjc.EVIDENCE_UNVERIFIED,
                    "uniqueness_detail": ("L1", "01", 1, 1),
                    "refused": True, "code": vjc.CODE_DUPLICATE_FOUND}
        return {"uniqueness_evidence": vjc.EVIDENCE_PROBE_CLEAN,
                "uniqueness_detail": None, "refused": False, "code": None}

    monkeypatch.setattr(vjc, "verify_uniqueness", fake_verify)
    rej = []
    out = vjc.load_verified_rules(object(), path=str(p), known_tables=TABLES,
                                  rejections=rej)
    assert [r["name"] for r in out] == ["good"], "a live-refused declaration survived"
    assert out[0]["uniqueness_evidence"] == vjc.EVIDENCE_PROBE_CLEAN
    assert _codes(rej) == [vjc.CODE_DUPLICATE_FOUND]
    assert rej[0]["subject"] == "dirty"

    # ①만 소비하면 둘 다 살아 나온다 ― 두 진입점의 차이가 곧 ②의 값이다.
    assert len(vjc.load_virtual_join_rules(path=str(p), known_tables=TABLES)) == 2


def test_unique_index_short_circuits_the_probe(monkeypatch):
    """영구 보장이 있으면 전수 스캔을 하지 않는다 ― 1,000만 행에서 약 11.6초짜리다."""
    monkeypatch.setattr(vjc, "unique_index_covering", lambda *a, **k: "uq_t")

    def explode(*a, **k):
        raise AssertionError("probed despite a UNIQUE index proving the property")

    monkeypatch.setattr(vjc, "probe_duplicate", explode)
    out = vjc.verify_uniqueness(object(), {"right_table": "t", "right_columns": ["a"]})
    assert out["uniqueness_evidence"] == vjc.EVIDENCE_UNIQUE_INDEX and not out["refused"]


# ---------------------------------------------------------------------------
# config_resolve_report 통합
# ---------------------------------------------------------------------------

@pytest.fixture
def vj_env(tmp_path, monkeypatch):
    """선언 dict를 파일로 써서 도메인 보고서를 만든다."""
    from database import crud
    saved = dict(crud.TABLE_CONFIG)

    def build(decls):
        p = tmp_path / "virtual_join_rules.json"
        p.write_text(json.dumps(decls, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(TABLES)
        return crr._resolve_virtual_join()

    yield build
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(saved)


def test_report_puts_a_fanout_declaration_in_rejected_with_scope_unresolved(vj_env):
    """거부는 운영자가 보는 자리에 이름과 함께 뜬다 ― 아무도 안 보는 로그가 아니라."""
    d = vj_env({"mapwide": _decl("vjoin_defect_map", "vjoin_fail_map",
                                 [("lot", "lot"), ("slot", "slot")], ["metro_eqp"])})
    assert d["counts"]["rejected"] == 1 and d["counts"]["effective"] == 0
    e = d["rejected"][0]
    assert e["subject"] == "mapwide"
    assert e["reason"] == crr.REASON_SCOPE_UNRESOLVED
    assert "불어납니다" in e["detail"], "the sentence must say what goes wrong"


def test_the_fanout_sentence_is_wholly_korean_and_names_what_to_fix(vj_env):
    """운영자가 읽는 최종 문장이 반쯤 영어면 그는 고칠 곳을 못 찾는다(INV-F9-8).

    로더의 `detail`은 영어 로그 문구다. 팬아웃 거부는 구조화된 사실(`facts`)이 오므로
    보고서가 그 영어를 이어 붙이지 않고 문장을 새로 짓는다.
    """
    d = vj_env({"mapwide": _decl("vjoin_defect_map", "vjoin_fail_map",
                                 [("lot", "lot"), ("slot", "slot")], ["metro_eqp"])})
    s = d["rejected"][0]["detail"]
    assert "join key does not select" not in s, "the English loader string leaked through"
    assert "vjoin_fail_map" in s, "the sentence must name the right table"
    assert "x, y" in s, "the sentence must name the columns the join key fails to fix"
    # 영어 단어가 남아 있으면 안 된다. 문장이 인용할 자격이 있는 ASCII는 이 선언에
    # 등장하는 **식별자**(테이블명·컬럼명)뿐이다 ― 그 밖의 영단어는 로더 문자열의 유출이다.
    identifiers = set(TABLES) | {c for t in TABLES.values() for c in t["column_types"]}
    for word in s.split():
        bare = word.strip(".,()").rstrip("은는이가을를의")
        if bare.isascii() and bare and bare[0].isalpha() and len(bare) > 2:
            assert bare in identifiers, f"English leaked into the operator sentence: {bare}"


def test_shape_errors_keep_the_loader_string_because_they_carry_no_facts(vj_env):
    """사실이 없는 거부까지 한국어로 지어내지는 않는다 ― 있는 것만 쓴다."""
    d = vj_env({"bad": _decl("vjoin_log", "nope_table", [("lot", "lot")], ["wafer_id"])})
    assert "nope_table" in d["rejected"][0]["detail"]


def test_report_uses_mapping_unavailable_for_shape_errors(vj_env):
    d = vj_env({"bad": _decl("vjoin_log", "nope_table",
                             [("lot", "lot")], ["wafer_id"])})
    assert d["rejected"][0]["reason"] == crr.REASON_MAPPING_UNAVAILABLE


def test_a_valid_declaration_is_not_reported_as_effective(vj_env):
    """조인을 실행하는 코드가 없으므로 `effective`는 거짓말이 된다."""
    d = vj_env({"wafer": _decl("vjoin_log", "vjoin_wafer_map",
                               [("lot", "lot"), ("slot", "slot")], ["wafer_id"])})
    assert d["counts"]["effective"] == 0 and d["counts"]["ineffective"] == 1
    e = d["ineffective"][0]
    assert e["reason"] == crr.REASON_NOT_REACHED
    assert e["fields"]["right_declared_key"] == ["lot", "slot"]
    assert e["fields"]["uniqueness_evidence"] == vjc.EVIDENCE_UNVERIFIED


def test_report_reasons_stay_inside_the_closed_vocabulary(vj_env):
    """새 단어는 계약 변경이다 ― 이 도메인은 하나도 만들지 않는다."""
    d = vj_env({"a": _decl("vjoin_defect_map", "vjoin_fail_map",
                           [("lot", "lot"), ("slot", "slot")], ["metro_eqp"]),
                "b": _decl("vjoin_log", "vjoin_wafer_map",
                           [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
                "c": _decl("vjoin_log", "nope", [("lot", "lot")], ["wafer_id"])})
    for pop in ("effective", "ineffective", "rejected"):
        for e in d[pop]:
            assert e["reason"] in (None,) + crr.REASONS
    assert set(vjc.EVIDENCE_GRADES) == {vjc.EVIDENCE_UNIQUE_INDEX,
                                        vjc.EVIDENCE_PROBE_CLEAN,
                                        vjc.EVIDENCE_UNVERIFIED}


def test_the_domain_is_registered_and_isolated(vj_env):
    assert crr.DOMAIN_VIRTUAL_JOIN in crr._RESOLVERS
    report = crr.resolve_report([crr.DOMAIN_VIRTUAL_JOIN])
    assert [d["domain"] for d in report["domains"]] == [crr.DOMAIN_VIRTUAL_JOIN]


def test_the_domain_issues_no_database_queries(vj_env, monkeypatch):
    """`/admin/config/resolve`는 요청 경로다. ②는 세션이 필요해 여기 없다."""
    import database.database as dbmod

    def explode(*a, **k):
        raise AssertionError("the virtual_join resolver opened a database session")

    monkeypatch.setattr(dbmod, "SessionLocal", explode)
    vj_env({"wafer": _decl("vjoin_log", "vjoin_wafer_map",
                           [("lot", "lot"), ("slot", "slot")], ["wafer_id"])})


# ---------------------------------------------------------------------------
# INV-F9-8 ― `detail`은 운영자가 읽는 최종 문장이다
# ---------------------------------------------------------------------------

def _all_details(domain):
    out = [s["detail"] for s in domain["sources"]] + [s["detail"] for s in domain["settings"]]
    for pop in ("effective", "ineffective", "rejected"):
        out += [e["detail"] for e in domain[pop]]
    return out


def test_every_operator_sentence_is_cp949_encodable_and_clean(vj_env):
    """운영 콘솔이 cp949다. 인코딩 못 하는 글자는 운영자에게 도달하지 못한다.

    함께 채점: Python repr(`['lot']`), 리터럴 마크다운(`**`), 이모지, 빈 문장.
    """
    d = vj_env({"a": _decl("vjoin_defect_map", "vjoin_fail_map",
                           [("lot", "lot"), ("slot", "slot")], ["metro_eqp"]),
                "b": _decl("vjoin_log", "vjoin_wafer_map",
                           [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
                "c": _decl("vjoin_log", "vjoin_process",
                           [("lot", "lot"), ("slot", "slot")], ["result"]),
                "d": _decl("vjoin_defect_map", "vjoin_fail_map",
                           [("lot", "lot")], ["metro_eqp"], join_cardinality="many")})
    for s in _all_details(d):
        assert s and s.strip(), "empty detail forces the client to compose its own sentence"
        try:
            s.encode("cp949")
        except UnicodeEncodeError as e:
            pytest.fail(f"detail is not cp949-encodable at {e.start}: {s!r}")
        assert "['" not in s and "']" not in s, f"Python list repr leaked: {s!r}"
        assert "**" not in s, f"literal markdown leaked: {s!r}"
        assert "—" not in s, "use U+2015 (―), not U+2014 (—) - cp949"
        for ch in s:
            assert not (0x1F300 <= ord(ch) <= 0x1FAFF), f"emoji in operator text: {s!r}"
            assert ord(ch) not in (0x26A0, 0xFE0F), f"warning-sign emoji in text: {s!r}"


def test_module_docstring_records_the_measurements_that_justify_the_guard():
    """수치가 사라지면 다음 사람이 가드를 「보수적인 취향」으로 읽고 지운다."""
    doc = vjc.__doc__
    for token in ("132,715,520", "1288", "2,552,624", "26.27%", "859", "11.6"):
        assert token in doc, f"missing measured justification: {token}"
