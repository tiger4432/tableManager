"""VIRTUAL JOIN 팬아웃 가드 ― UNIQUE 인덱스가 없으면 거부되는가.

무엇을 지키는가 (사용자 2026-07-31)
    「인덱스 없으면 거절해」 · 「유니크 INDEX 걸면 그냥 DB 영속 아닌가」
    승인 조건은 하나다 ― 조인 키를 덮는 **유효한 UNIQUE 인덱스**. 인덱스는 config가
    아니라 데이터베이스에 살아서 이후의 어떤 쓰기도 그 성질을 깨지 못한다. 그래서
    등급도 스냅샷도 예산도 없다.

이 파일의 기준선은 상상이 아니라 **실측**이다 (운영 DB read-only, 2026-07-31):
    core_defect_map ⋈ eds_fail_map (lot,slot,x,y)   103,040 →     103,040   x1
    core_defect_map ⋈ eds_fail_map (lot,slot)       103,040 → 132,715,520   x1288
    bonding_log     ⋈ wafer_process (lot,slot)       14,436 →   2,552,624   x177
    dt_log          ⋈ core_wafer_map (core_lot,core_slot)  768 →      768   x1.00

마지막 줄이 사용자가 실제로 원하는 시나리오다. **왼쪽이 키당 128행인데 그것은 팬아웃이
아니라 이 기능의 목적**이므로, 가드가 그 모양을 잡으면 안 된다 ― 검사는 오른쪽에만 건다.

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
# 실측 케이스를 재현하는 table_config
# ---------------------------------------------------------------------------

# 컬럼 집합은 운영 table_config 그대로다 ― `metro_eqp`는 eds_fail_map 에만 있고
# core_defect_map 에는 없다. 양쪽에 다 넣으면 shadow 가드가 먼저 걸려 유일성 가드가
# 한 번도 실행되지 않는다(그 상태로 통과하는 테스트는 아무것도 증명하지 않는다).
MAP_COLS = {"lot": "string", "slot": "string", "x": "number", "y": "number",
            "val": "string", "chip_key": "string"}

TABLES = {
    "vjoin_defect_map": {
        "business_key": "chip_key",
        "composite_key_source": ["lot", "slot", "x", "y"],
        "column_types": dict(MAP_COLS),
    },
    "vjoin_fail_map": {
        "business_key": "chip_key",
        "composite_key_source": ["lot", "slot", "x", "y"],
        "column_types": dict(MAP_COLS, metro_eqp="string"),
    },
    # 파생 테이블 (core_wafer_map 모양) ― 사용자 시나리오의 오른쪽
    "vjoin_wafer_map": {
        "business_key": "core_key",
        "composite_key_source": ["lot", "slot"],
        "column_types": {"core_key": "string", "lot": "string", "slot": "string",
                         "wafer_id": "string", "chip_count": "number"},
    },
    "vjoin_process": {
        "business_key": "proc_id",
        "column_types": {"proc_id": "string", "lot": "string", "slot": "string",
                         "eqp_id": "string", "result": "string"},
    },
    # 로그성 테이블 (dt_log/bonding_log 모양) ― 왼쪽. 키당 여러 행이 정상이다.
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
    rejections = []
    rules = vjc.validate_virtual_join_rules(
        decls, known_tables=TABLES if tables is None else tables,
        rejections=rejections)
    return rules, rejections


def _codes(rejections):
    return [r.get("code") for r in rejections]


class FakeDB:
    """`pg_index` 조회의 대역. `indexes`는 {테이블: {인덱스명: [컬럼...]}}.

    🔴 **테이블별로 갈라야 한다.** 처음엔 인덱스 목록 하나만 들고 모든 조회에 같은
    행을 돌려줬는데, 그러면 인덱스가 없는 테이블까지 통과해 `load_verified_rules`가
    아무것도 거르지 않는 상태로 테스트가 초록이 된다(실제로 그렇게 났다). 대역이
    `:t` 바인드를 무시하면 그 바인드를 쓰는 코드는 검사되지 않는다.
    """

    def __init__(self, indexes=None, dialect="postgresql"):
        self._by_table = {t: sorted((n, list(c)) for n, c in idx.items())
                          for t, idx in (indexes or {}).items()}
        self._dialect = dialect
        self.queries = 0
        self.asked = []

    def get_bind(self):
        outer = self

        class B:
            class dialect:
                name = outer._dialect
        return B()

    def execute(self, stmt, params=None, *a, **k):
        self.queries += 1
        table = (params or {}).get("t")
        self.asked.append(table)
        rows = self._by_table.get(table, [])

        class R:
            def fetchall(self_inner):
                return rows
        return R()


# ---------------------------------------------------------------------------
# 유일성 게이트 ― UNIQUE 인덱스가 유일한 승인 근거
# ---------------------------------------------------------------------------

def test_no_unique_index_is_a_refusal():
    """실측 x1288도 x177도 여기서 걸린다 ― 근거가 하나뿐이라 케이스가 갈리지 않는다."""
    rule = {"right_table": "vjoin_fail_map", "right_columns": ["lot", "slot"]}
    out = vjc.verify_uniqueness(FakeDB({"vjoin_fail_map": {}}), rule)
    assert out["refused"] is True
    assert out["code"] == vjc.CODE_NO_UNIQUE_INDEX
    assert out["unique_index"] is None


def test_a_covering_unique_index_accepts():
    rule = {"right_table": "vjoin_wafer_map", "right_columns": ["lot", "slot"]}
    out = vjc.verify_uniqueness(FakeDB({"vjoin_wafer_map": {"uq_w": ["lot", "slot"]}}), rule)
    assert out["refused"] is False and out["unique_index"] == "uq_w"


def test_unique_index_on_a_subset_is_enough():
    """`(a)`에 UNIQUE가 있으면 `(a,b)`로도 유일하다."""
    rule = {"right_table": "t", "right_columns": ["lot", "slot"]}
    assert vjc.verify_uniqueness(FakeDB({"t": {"uq_lot": ["lot"]}}), rule)["refused"] is False


def test_a_unique_index_the_join_key_does_not_cover_is_not_evidence():
    """조인 키 밖의 컬럼에 걸린 UNIQUE는 이 조인의 유일성을 말하지 않는다."""
    rule = {"right_table": "t", "right_columns": ["lot", "slot"]}
    assert vjc.verify_uniqueness(FakeDB({"t": {"uq_chip": ["chip_key"]}}), rule)["refused"] is True


def test_non_postgres_is_refused_not_assumed_clean():
    """모르는 것은 모른다고 한다 ― 안전한 방향의 무지."""
    db = FakeDB({"t": {"uq_all": ["lot"]}}, dialect="sqlite")
    rule = {"right_table": "t", "right_columns": ["lot"]}
    assert vjc.verify_uniqueness(db, rule)["refused"] is True
    assert db.queries == 0, "must not query a non-postgres catalog"


def test_the_catalog_query_excludes_the_three_lookalikes():
    """무효·부분·표현식 인덱스는 「UNIQUE 인덱스가 있다」로 읽히지만 유일성이 아니다.

    배제가 SQL의 WHERE 절에 있으므로 그 절이 사라지면 이 테스트가 잡는다.
    사용자 확정의 근거 전체가 이 세 조건 위에 서 있다.
    """
    import inspect
    sql = inspect.getsource(vjc.unique_index_covering)
    assert "x.indisunique" in sql
    assert "x.indisvalid" in sql, "an INVALID index (cancelled CONCURRENTLY) would count"
    assert "x.indpred IS NULL" in sql, "a partial index is unique only inside its predicate"
    assert "x.indexprs IS NULL" in sql, "an expression index is unique on the expression"


def test_uniqueness_is_checked_on_the_right_side_only(monkeypatch):
    """사용자 시나리오: 왼쪽이 키당 128행이어도 통과해야 한다 ― 그것이 조인의 목적이다.

    `dt_log → core_wafer_map (core_lot, core_slot)` = 768행 → 768행(x1.00), 실측.
    가드가 왼쪽 다중도를 본다면 이 모양이 잡히고 기능 자체가 죽는다.
    """
    seen = {}

    def spy(db, table, columns):
        seen["table"] = table
        seen["columns"] = list(columns)
        return "uq_w"

    monkeypatch.setattr(vjc, "unique_index_covering", spy)
    rules, rej = _load({"scenario": _decl("vjoin_log", "vjoin_wafer_map",
                                          [("lot", "lot"), ("slot", "slot")],
                                          ["wafer_id"])})
    assert rej == []
    out = vjc.verify_uniqueness(object(), rules[0])
    assert out["refused"] is False
    assert seen["table"] == "vjoin_wafer_map", "the guard looked at the wrong side"
    assert seen["columns"] == ["lot", "slot"]


# ---------------------------------------------------------------------------
# 거부는 운영자가 행동할 수 있어야 한다
# ---------------------------------------------------------------------------

def test_the_declaration_carries_the_index_the_operator_must_create():
    rules, _ = _load({"r": _decl("vjoin_log", "vjoin_wafer_map",
                                 [("lot", "lot"), ("slot", "slot")], ["wafer_id"])})
    ddl = rules[0]["required_index_ddl"]
    assert "CREATE UNIQUE INDEX" in ddl
    assert "vjoin_wafer_map" in ddl and '"lot"' in ddl and '"slot"' in ddl
    assert rules[0]["required_index"] == "uq_vjoin_vjoin_wafer_map_lot_slot"


def test_the_index_name_stays_inside_the_postgres_identifier_limit():
    """63바이트를 넘으면 PostgreSQL이 조용히 잘라 다른 인덱스를 가리킨다."""
    long_cols = ["c%02d_very_long_column_name" % i for i in range(6)]
    name = vjc.required_index_name("a_rather_long_table_name_here", long_cols)
    assert len(name.encode("utf-8")) <= 63
    assert name.startswith(vjc.INDEX_PREFIX)
    # 접혀도 서로 다른 키는 서로 다른 이름이어야 한다.
    other = vjc.required_index_name("a_rather_long_table_name_here",
                                    long_cols[:-1] + ["zzz_other_column_name_here"])
    assert name != other


def test_verification_report_tells_each_declaration_what_it_needs(tmp_path):
    p = tmp_path / "vj.json"
    p.write_text(json.dumps({
        "ok": _decl("vjoin_log", "vjoin_wafer_map",
                    [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
        "bad": _decl("vjoin_defect_map", "vjoin_fail_map",
                     [("lot", "lot"), ("slot", "slot")], ["metro_eqp"]),
    }), encoding="utf-8")
    db = FakeDB({"vjoin_wafer_map": {"uq_vjoin_vjoin_wafer_map_lot_slot": ["lot", "slot"]}})
    rep = vjc.verification_report(db, path=str(p), known_tables=TABLES)
    by = {d["name"]: d for d in rep["declarations"]}
    assert rep["accepted"] == 1 and rep["refused"] == 1
    assert by["ok"]["accepted"] and by["ok"]["required_index_ddl"] is None
    assert not by["bad"]["accepted"]
    assert "CREATE UNIQUE INDEX" in by["bad"]["required_index_ddl"]
    assert "vjoin_fail_map" in by["bad"]["required_index_ddl"]


def test_the_refusal_sentence_is_wholly_korean_and_carries_the_ddl(tmp_path):
    """거부는 운영자가 읽는 **완성된 한국어 문장**으로 자기를 설명하고 DDL을 준다.

    이 분기는 세션이 있어야 나오는 코드(`no_unique_index`)라 DB 없는 해석 보고서
    경로에서는 발화하지 않는다 ― 그래서 라우트 쪽 경로로 채점해야 한다. 결함 주입에서
    이 테스트가 없을 때 「사유 문장 조립을 꺼도 전부 초록」이 나왔고, 그것이 이 테스트가
    생긴 이유다.
    """
    p = tmp_path / "vj.json"
    p.write_text(json.dumps({
        "bad": _decl("vjoin_defect_map", "vjoin_fail_map",
                     [("lot", "lot"), ("slot", "slot")], ["metro_eqp"]),
    }), encoding="utf-8")
    rep = vjc.verification_report(FakeDB({}), path=str(p), known_tables=TABLES)
    s = rep["declarations"][0]["detail"]
    assert s and "CREATE UNIQUE INDEX" in s
    assert "vjoin_fail_map" in s
    assert "no valid UNIQUE index" not in s, "the English loader string leaked"
    s.encode("cp949")
    # 식별자·DDL 키워드를 뺀 나머지는 한국어여야 한다.
    allowed = (set(TABLES) | {c for t in TABLES.values() for c in t["column_types"]}
               | {"CREATE", "UNIQUE", "INDEX", "CONCURRENTLY", "ON"}
               | {vjc.required_index_name("vjoin_fail_map", ["lot", "slot"])})
    for word in s.split():
        bare = word.strip('.,()";').rstrip("은는이가을를의")
        if bare.isascii() and bare and bare[0].isalpha() and len(bare) > 2:
            assert bare in allowed, f"English leaked into the operator sentence: {bare}"


def test_report_and_route_use_one_sentence_composer():
    """같은 거부가 두 화면에서 다른 문장으로 나오면 「서버가 정본」 계약이 깨진다."""
    facts = {"right_table": "t", "join_key": ["lot"],
             "required_index": "uq_t_lot", "required_index_ddl": "CREATE UNIQUE INDEX x;"}
    assert crr.virtual_join_detail(vjc.CODE_NO_UNIQUE_INDEX, facts) == \
        crr.virtual_join_detail("no_unique_index", facts)
    # 사실이 없으면 로더 문구를 그대로 나른다 ― 없는 문장을 지어내지 않는다.
    assert "boom" in crr.virtual_join_detail(vjc.CODE_SHAPE, None, "boom")


def test_load_verified_rules_drops_what_has_no_index(tmp_path):
    """조인을 실행하는 코드의 유일한 진입점 ― 모양만 통과한 선언은 여기서 걸러진다."""
    p = tmp_path / "vj.json"
    p.write_text(json.dumps({
        "ok": _decl("vjoin_log", "vjoin_wafer_map",
                    [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
        "bad": _decl("vjoin_defect_map", "vjoin_fail_map",
                     [("lot", "lot"), ("slot", "slot")], ["metro_eqp"]),
    }), encoding="utf-8")
    db = FakeDB({"vjoin_wafer_map": {"uq_vjoin_vjoin_wafer_map_lot_slot": ["lot", "slot"]}})
    rej = []
    out = vjc.load_verified_rules(db, path=str(p), known_tables=TABLES, rejections=rej)
    assert [r["name"] for r in out] == ["ok"]
    assert out[0]["unique_index"] == "uq_vjoin_vjoin_wafer_map_lot_slot"
    assert _codes(rej) == [vjc.CODE_NO_UNIQUE_INDEX]
    assert rej[0]["facts"]["required_index_ddl"].startswith("CREATE UNIQUE INDEX")

    # 모양만 보는 로더는 둘 다 통과시킨다 ― 두 진입점의 차이가 곧 게이트의 값이다.
    assert len(vjc.load_virtual_join_rules(path=str(p), known_tables=TABLES)) == 2


# ---------------------------------------------------------------------------
# 모양 검증
# ---------------------------------------------------------------------------

def test_aggregate_form_is_a_named_refusal_not_an_escape_hatch():
    """유일성 요구를 끄는 스위치는 그것이 향할 안전한 경로가 생긴 뒤에 열린다."""
    rules, rej = _load({"agg": _decl("vjoin_defect_map", "vjoin_fail_map",
                                     [("lot", "lot"), ("slot", "slot")],
                                     ["metro_eqp"], join_cardinality="many")})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_FANOUT_DECLARED]


def test_duplicate_right_binding_is_rejected():
    """같은 오른쪽 컬럼을 두 번 묶으면 키가 넓어 보이지만 고정하는 성분은 하나다."""
    rules, rej = _load({"dup": _decl("vjoin_defect_map", "vjoin_fail_map",
                                     [("lot", "lot"), ("slot", "slot"),
                                      ("x", "lot"), ("y", "lot")],
                                     ["metro_eqp"])})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_SHAPE]


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
    rules, rej = _load({"shadow": _decl("vjoin_log", "vjoin_wafer_map",
                                        [("lot", "lot"), ("slot", "slot")],
                                        ["slot"])})
    assert rules == []
    assert _codes(rej) == [vjc.CODE_SHAPE] and "slot" in rej[0]["detail"]


def test_sql_identifier_shape_is_enforced_before_the_ddl_is_assembled():
    """이름이 인덱스 DDL 문장에 보간되므로 형태 검증이 조립보다 먼저 온다."""
    for bad in ['lot" OR "1"="1', "lot;drop", "1lot", ""]:
        rules, _ = _load({"inj": _decl("vjoin_log", "vjoin_wafer_map",
                                       [(bad, "lot"), ("slot", "slot")], ["wafer_id"])})
        assert rules == [], f"{bad!r} was admitted as a column name"
        rules, _ = _load({"inj": _decl("vjoin_log", "vjoin_wafer_map",
                                       [("lot", "lot"), ("slot", "slot")], [bad or "x"])})
        assert rules == [], f"{bad!r} was admitted as an expose column"
    for bad_table in ['t" ; drop', "1t", "t-x"]:
        rules, _ = _load({"inj": _decl(bad_table, "vjoin_wafer_map",
                                       [("lot", "lot")], ["wafer_id"])})
        assert rules == [], f"{bad_table!r} was admitted as a table name"


def test_the_generated_ddl_never_carries_a_caller_string():
    """DDL은 이 파일이 조립한 식별자만 싣는다 ― 형태 검증을 통과한 이름뿐이다."""
    ddl = vjc.required_index_ddl("vjoin_wafer_map", ["lot", "slot"])
    assert ddl == ('CREATE UNIQUE INDEX CONCURRENTLY uq_vjoin_vjoin_wafer_map_lot_slot '
                   'ON "vjoin_wafer_map" ("lot", "slot");')


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
    assert vjc.load_virtual_join_rules(path=str(p), known_tables=TABLES,
                                       rejections=rej) == []
    assert len(rej) == 1 and rej[0]["scope"] == "file"


def test_non_object_root_is_rejected(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[]", encoding="utf-8")
    rej = []
    assert vjc.load_virtual_join_rules(path=str(p), known_tables=TABLES,
                                       rejections=rej) == []
    assert rej and rej[0]["scope"] == "file"


def test_the_shipped_sample_documents_the_index_requirement():
    sample = os.path.join(_SERVER, "config", "virtual_join_rules.json.sample")
    raw = json.loads(open(sample, encoding="utf-8").read())
    blob = json.dumps(raw, ensure_ascii=False)
    assert "UNIQUE" in blob, "the sample must state the accepting condition"
    ex = raw["_example_rejected_no_unique_index"]
    assert [p["right"] for p in ex["join_key"]] == ["lot", "slot"]


# ---------------------------------------------------------------------------
# config_resolve_report 통합
# ---------------------------------------------------------------------------

@pytest.fixture
def vj_env(tmp_path, monkeypatch):
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


def test_no_declaration_is_ever_effective_in_the_db_free_report(vj_env):
    """승인은 `pg_index`가 아는 사실이다. 설정 파일만 읽는 화면은 승인할 수 없다."""
    d = vj_env({"r": _decl("vjoin_log", "vjoin_wafer_map",
                           [("lot", "lot"), ("slot", "slot")], ["wafer_id"])})
    assert d["counts"]["effective"] == 0 and d["counts"]["ineffective"] == 1
    e = d["ineffective"][0]
    assert e["reason"] == crr.REASON_NOT_REACHED
    assert "CREATE UNIQUE INDEX" in e["detail"], (
        "a refusal that does not name the index is one the operator cannot act on")
    assert e["fields"]["required_index_ddl"].startswith("CREATE UNIQUE INDEX")


def test_the_report_names_the_verify_route_for_the_half_it_cannot_answer(vj_env):
    d = vj_env({"r": _decl("vjoin_log", "vjoin_wafer_map",
                           [("lot", "lot"), ("slot", "slot")], ["wafer_id"])})
    assert "/admin/config/virtual-join/verify" in d["ineffective"][0]["detail"]


def test_codes_map_into_the_closed_vocabulary():
    assert crr._VJ_CODE_TO_REASON[vjc.CODE_NO_UNIQUE_INDEX] == crr.REASON_SCOPE_UNRESOLVED
    assert crr._VJ_CODE_TO_REASON[vjc.CODE_FANOUT_DECLARED] == crr.REASON_MAPPING_UNAVAILABLE
    assert crr._VJ_CODE_TO_REASON[vjc.CODE_SHAPE] == crr.REASON_MAPPING_UNAVAILABLE
    assert set(crr._VJ_CODE_TO_REASON.values()) <= set(crr.REASONS)


def test_report_uses_mapping_unavailable_for_shape_errors(vj_env):
    d = vj_env({"bad": _decl("vjoin_log", "nope_table",
                             [("lot", "lot")], ["wafer_id"])})
    assert d["rejected"][0]["reason"] == crr.REASON_MAPPING_UNAVAILABLE
    assert "nope_table" in d["rejected"][0]["detail"]


def test_report_reasons_stay_inside_the_closed_vocabulary(vj_env):
    """새 단어는 계약 변경이다 ― 이 도메인은 하나도 만들지 않는다."""
    d = vj_env({"a": _decl("vjoin_defect_map", "vjoin_fail_map",
                           [("lot", "lot"), ("slot", "slot")], ["metro_eqp"],
                           join_cardinality="many"),
                "b": _decl("vjoin_log", "vjoin_wafer_map",
                           [("lot", "lot"), ("slot", "slot")], ["wafer_id"]),
                "c": _decl("vjoin_log", "nope", [("lot", "lot")], ["wafer_id"])})
    for pop in ("effective", "ineffective", "rejected"):
        for e in d[pop]:
            assert e["reason"] in (None,) + crr.REASONS


def test_the_domain_is_registered_and_isolated(vj_env):
    assert crr.DOMAIN_VIRTUAL_JOIN in crr._RESOLVERS
    report = crr.resolve_report([crr.DOMAIN_VIRTUAL_JOIN])
    assert [d["domain"] for d in report["domains"]] == [crr.DOMAIN_VIRTUAL_JOIN]


def test_the_domain_issues_no_database_queries(vj_env, monkeypatch):
    """`/admin/config/resolve`는 요청 경로다. 유일성 검사는 verify 라우트로 갈라져 있다."""
    import database.database as dbmod

    def explode(*a, **k):
        raise AssertionError("the virtual_join resolver opened a database session")

    monkeypatch.setattr(dbmod, "SessionLocal", explode)
    vj_env({"r": _decl("vjoin_log", "vjoin_wafer_map",
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
    for token in ("132,715,520", "1288", "2,552,624", "26.27%", "768"):
        assert token in doc, f"missing measured justification: {token}"


def test_the_probe_machinery_is_gone(vj_env):
    """게이트가 아니게 된 안전장치는 지운다 ― 남아 있으면 무언가 검사된다고 읽힌다.

    사용자 확정(2026-07-31)으로 승인 근거가 UNIQUE 인덱스 하나가 되면서 예산·
    `statement_timeout`·`incomplete` 상태는 소비자를 잃었다. 죽은 안전장치는 없느니만
    못하다 ― 다음 읽는 사람이 무언가 검사되고 있다고 가정하기 때문이다.
    """
    for gone in ("probe_duplicate", "DEFAULT_PROBE_BUDGET_MS", "MAX_PROBE_BUDGET_MS",
                 "EVIDENCE_PROBE_CLEAN", "EVIDENCE_UNVERIFIED", "EVIDENCE_GRADES",
                 "CODE_DUPLICATE_FOUND", "CODE_PROBE_INCOMPLETE",
                 "key_is_covered", "declared_key_columns"):
        assert not hasattr(vjc, gone), f"dead safety machinery survived: {gone}"
    d = vj_env({})
    assert not any(s["key"] == "probe_budget_ms" for s in d["settings"])
