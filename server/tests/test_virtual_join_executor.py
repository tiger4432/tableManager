"""VIRTUAL JOIN 실행기 ― 조인이 실제로 도는가, 그리고 **틀리면 빨개지는가**.

가드(`test_virtual_join_guard.py`)는 선언이 승인되는가를 본다. 이 파일은 승인된 선언이
행 페이로드에 어떻게 착지하는가를 본다.

여기 있는 모든 기제는 **RED로 갈 수 있음이 증명돼 있다**(server-pm 교훈: 새로 쓴 줄을
한 번도 실행하지 않는 검증으로 "해소"를 선언하지 말 것):

  - ②(맞는 행은 있는데 값이 빔)를 지우면 `test_matched_but_empty_...`가 빨개진다.
    실측 26.27%가 그 분기이고, 그것 없이는 빈 값이 「값이 있다」로 읽힌다.
  - absent-only를 지우면 `test_left_value_is_byte_identical_...`이 빨개진다.
  - 유일성 게이트를 우회하면 `test_an_unverified_declaration_produces_no_join_at_all`이
    빨개진다(이 테스트만 `unique_index_covering`을 가짜로 만들지 **않는다**).
  - 쓰기 거부를 빼면 `test_write_to_a_virtual_column_is_refused_*` 3종이 빨개진다.
  각 항목에 대해 **결함 주입 확인**을 실제로 돌렸고, 무엇을 지웠을 때 어느 테스트가
  깨지는지는 각 테스트 docstring에 적었다.

[격리] 테이블명은 `vjx_test_` 접두 ― 사용자 gitignored config에 실존할 수 없다.
겹치면 import 시점 `init_dynamic_models`가 공유 sqlite에 실 스키마를 선점하고
`create_all(checkfirst)`이 우리 것을 건너뛴다(server-pm 교훈: `bonding_log` 함정).

[왜 `unique_index_covering`을 가짜로 만드는가] 승인 근거는 `pg_index`인데 이 스위트는
sqlite로 돈다 ― `unique_index_covering`은 postgresql이 아니면 **항상 None**이다(모르면
거부). 그대로 두면 이 파일의 모든 테스트가 "조인 0건"을 관측하며 초록이 되고 실행기는
한 줄도 실행되지 않는다. 그래서 승인만 대역으로 세우고, 대역 없는 경로는 전용 테스트가
따로 지킨다.
"""
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

JOIN_TABLES = {
    # 왼쪽 ― 로그 모양. 키당 여러 행이 정상이다(그것이 조인의 용도).
    "vjx_test_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string", "core_slot": "string",
            "eqp_id": "string",
            # 🔴 충돌 컬럼. 운영 `dt_log`가 lot/slot 대신 `wafer_id`를 직접 실어 오는
            # 행을 섞어 두는 그 모양이다 ― 오른쪽에도 같은 이름이 있다.
            "wafer_id": "string",
        },
    },
    # 오른쪽 ― 웨이퍼 마스터. (core_lot, core_slot)로 유일하다.
    "vjx_test_wafer": {
        "business_key": "wafer_key",
        "composite_key_source": ["core_lot", "core_slot"],
        "column_types": {
            "wafer_key": "string", "core_lot": "string", "core_slot": "string",
            "wafer_id": "string", "fab_site": "string",
        },
    },
}

KEY_PAIRS = [{"left": "core_lot", "right": "core_lot"},
             {"left": "core_slot", "right": "core_slot"}]


def _decl(expose, **extra):
    d = {"left_table": "vjx_test_log", "right_table": "vjx_test_wafer",
         "join_key": [dict(p) for p in KEY_PAIRS], "expose": list(expose)}
    d.update(extra)
    return d


def _seed(db, table, rows, source_name="pipeline_parser"):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"seed_{table}", silent=True))


def _seed_raw(db, table, rows):
    """모델에 **직접** 넣는다 ― 빈 문자열을 빈 문자열 그대로 착지시키기 위해서다.

    `crud.apply_batch_updates`를 타면 `cast_value_by_type`이 `""`와 `"   "`를 **NULL로
    정규화**한다. 그래서 그 경로로는 ②의 두 얼굴 중 「행은 있는데 값이 NULL」만 만들 수
    있고 「행은 있는데 값이 빈 문자열」은 **재현되지 않는다** ― 그 상태로 통과하는
    테스트는 `clean_str_value` 대신 `is not None`을 써도 초록이다(실제로 그랬다).

    컬럼은 `""`를 담을 수 있고, `virtual_join_config`의 경계 계약도 ②를
    「matched but NULL/빈 문자열」로 **둘 다** 명시한다. 실행기는 자기가 소유하지 않은
    상류 정규화 불변식에 기대면 안 된다 ― 이 헬퍼가 그 가정을 깨는 픽스처다.
    """
    import uuid6
    model = models.DYNAMIC_TABLES[table]
    bk = crud.TABLE_CONFIG[table].get("business_key")
    for r in rows:
        db.add(model(row_id=str(uuid6.uuid7()),
                     business_key_val=str(r.get(bk, "")).strip() or None, **r))
    db.flush()


@pytest.fixture()
def join_env(db_session, tmp_path, monkeypatch):
    """승인된 선언 1건(`fab_site`=virtual_only, `wafer_id`=collide)이 걸린 환경."""
    models.init_dynamic_models(JOIN_TABLES)
    crud.TABLE_CONFIG.update(JOIN_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    rules_path = tmp_path / "virtual_join_rules.json"
    rules_path.write_text(json.dumps({"vjx_rule": _decl(["wafer_id", "fab_site"])}),
                          encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(rules_path))
    vjx.reset_cache()
    yield db_session
    vjx.reset_cache()


@pytest.fixture()
def approved(monkeypatch):
    """`pg_index` 승인의 대역. sqlite에서는 실물이 항상 None을 돌려준다(위 docstring)."""
    def _covering(db, table, columns):
        if table == "vjx_test_wafer" and set(columns) <= {"core_lot", "core_slot"}:
            return "uq_vjoin_vjx_test_wafer_core_lot_core_slot"
        return None
    monkeypatch.setattr(vjc, "unique_index_covering", _covering)
    vjx.reset_cache()
    return _covering


def _payload(db, table="vjx_test_log"):
    """실제 행 조회 경로가 만드는 페이로드 ― 실행기를 우회하지 않는다."""
    import main
    model = models.DYNAMIC_TABLES[table]
    rows = db.query(model).order_by(model.business_key_val).all()
    user_cols = [c for c in JOIN_TABLES[table]["column_types"]]
    return {d["data"].get("log_id", {}).get("value"): d["data"]
            for d in main.fetch_and_merge_metadata(db, table, rows, user_cols,
                                                   include_sources=True)}


# ---------------------------------------------------------------------------
# 미상 ― ①(오른쪽 행 없음)과 ②(행은 있는데 값이 빔)를 **둘 다** 덮는가
# ---------------------------------------------------------------------------

def test_matched_but_empty_lands_on_the_unresolved_label(join_env, approved):
    """🔴 **②를 빼면 이 테스트가 빨개진다** ― 이 파일의 핵심 회귀다.

    실측(2026-07-31): `bonding_log → core_wafer_map.wafer_id`는 14,436행 **전부**가
    오른쪽 행을 찾지만 3,792행(26.27%)의 `wafer_id`가 비어 있다. 평범한 LEFT 조인은
    ①만 잡으므로 그 26%를 빈 문자열 그대로 돌려주고, 분석가는 「값이 있다」로 읽는다.

    결함 주입 확인(실제로 돌렸다): `_resolve_one`의 두 번째 분기를
    `if joined_value is not None:` 로 바꾸면 `L2`가 `미상` 대신 `""`를 실어 깨진다.
    ⚠️ 그 확인을 처음 돌렸을 때 **초록이었다** ― `_seed`(=`apply_batch_updates`)가
    `cast_value_by_type`으로 `""`를 NULL로 정규화해서 ②의 빈 문자열 얼굴이 픽스처에
    한 번도 나타나지 않았기 때문이다. `_seed_raw`가 그 정규화를 우회한다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [
        # 오른쪽 행이 **있고** 값도 있다
        {"wafer_key": "K1", "core_lot": "LOT-A", "core_slot": "01",
         "wafer_id": "WF-1", "fab_site": "M1"},
    ])
    # ②의 두 얼굴. NULL 쪽은 `is not None`으로도 잡히지만 빈 문자열 쪽은 아니다 ―
    # 둘 다 있어야 이 테스트가 분기 제거를 감지한다.
    _seed_raw(db, "vjx_test_wafer", [
        {"wafer_key": "K2", "core_lot": "LOT-A", "core_slot": "02",
         "wafer_id": "WF-2", "fab_site": ""},        # ② 빈 문자열
        {"wafer_key": "K4", "core_lot": "LOT-A", "core_slot": "04",
         "wafer_id": "WF-4", "fab_site": None},      # ② NULL
    ])
    _seed(db, "vjx_test_log", [
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01", "eqp_id": "E1"},
        {"log_id": "L2", "core_lot": "LOT-A", "core_slot": "02", "eqp_id": "E2"},
        # 오른쪽 행이 **아예 없다** ― 이것이 ①
        {"log_id": "L3", "core_lot": "LOT-Z", "core_slot": "99", "eqp_id": "E3"},
        {"log_id": "L4", "core_lot": "LOT-A", "core_slot": "04", "eqp_id": "E4"},
    ])
    cells = _payload(db)

    assert cells["L1"]["fab_site"]["value"] == "M1"      # 값이 있는 경우
    assert cells["L2"]["fab_site"]["value"] == "미상"     # ② matched-but-EMPTY STRING
    assert cells["L3"]["fab_site"]["value"] == "미상"     # ① no right row
    assert cells["L4"]["fab_site"]["value"] == "미상"     # ② matched-but-NULL


def test_the_two_unresolved_cases_stay_separately_observable(join_env, approved):
    """①과 ②가 같은 `미상`으로 접히더라도 실행기 안에서는 **갈라져 있어야** 한다.

    갈라져 있지 않으면 ②를 지웠을 때 아무 테스트도 빨개지지 않는다 ― 두 분기가
    한 값으로 접히는 순간 회귀 감지가 사라진다. `matched`가 그 증거다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K2", "core_lot": "LOT-A",
                                  "core_slot": "02", "wafer_id": "", "fab_site": ""}])
    _seed(db, "vjx_test_log", [
        {"log_id": "L2", "core_lot": "LOT-A", "core_slot": "02"},
        {"log_id": "L3", "core_lot": "LOT-Z", "core_slot": "99"},
    ])
    rules = vjx.rules_for(db, "vjx_test_log")
    assert len(rules) == 1
    model = models.DYNAMIC_TABLES["vjx_test_log"]
    ids = {r.business_key_val: r.row_id for r in db.query(model).all()}
    out = vjx.execute_rule(db, rules[0], list(ids.values()))

    assert out[ids["L2"]]["matched"] is True, "② 는 오른쪽 행을 찾은 경우다"
    assert out[ids["L3"]]["matched"] is False, "① 은 오른쪽 행이 없는 경우다"


def test_the_executor_returns_a_row_for_every_left_row_inner_would_not(join_env, approved):
    """INNER 금지가 **관측되는 자리는 여기**다 ― 페이지가 아니라 실행기 출력이다.

    처음엔 이것을 페이로드 행 수로 재려 했는데 그 단언은 **절대 깨지지 않는다**:
    페이지의 행 집합은 왼쪽 질의가 이미 확정했고, `attach`는 조인 결과에 없는 row_id를
    `matched=False`로 채워 `미상`을 준다. 그래서 INNER로 바꿔도 페이로드는 똑같다
    (결함 주입에서 실제로 초록이었다).

    INNER가 실제로 부수는 것은 **①과 ②를 가르는 능력**이다. 오른쪽이 없는 왼쪽 행이
    출력에서 통째로 빠지므로 `matched=False`라는 관측이 사라지고, 그러면 ②를 지워도
    아무 테스트가 빨개지지 않는 상태로 되돌아간다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-1", "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"},
        {"log_id": "L9", "core_lot": "NO-MATCH", "core_slot": "77"},
    ])
    model = models.DYNAMIC_TABLES["vjx_test_log"]
    row_ids = [r.row_id for r in db.query(model).all()]
    out = vjx.execute_rule(db, vjx.rules_for(db, "vjx_test_log")[0], row_ids)

    assert set(out) == set(row_ids), (
        "INNER 조인이면 오른쪽이 없는 왼쪽 행이 실행기 출력에서 사라진다")
    # 그리고 페이지 자체는 어느 쪽이든 온전하다 ― 그 사실도 함께 고정한다.
    assert set(_payload(db)) == {"L1", "L9"}


def test_left_multiplicity_is_not_fanout(join_env, approved):
    """왼쪽이 같은 키를 여러 번 갖는 것은 정상이며 **이 기능의 목적**이다.

    실측 `dt_log → core_wafer_map`는 왼쪽이 키당 128행이고 결과는 768 → 768(x1.00).
    출력 행 수가 입력 행 수와 같아야 한다 ― 오른쪽 유일성이 그것을 보장한다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-1", "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [{"log_id": f"L{i}", "core_lot": "LOT-A",
                                "core_slot": "01"} for i in range(12)])
    cells = _payload(db)
    assert len(cells) == 12
    assert all(c["fab_site"]["value"] == "M1" for c in cells.values())


# ---------------------------------------------------------------------------
# 충돌 ― absent-only. 왼쪽 값이 있으면 **한 바이트도** 바뀌지 않는다
# ---------------------------------------------------------------------------

def test_left_value_is_byte_identical_before_and_after_the_feature(join_env, approved):
    """🔴 **absent-only를 빼면 이 테스트가 빨개진다.**

    왼쪽에 값이 있는 셀은 조인이 있든 없든 페이로드가 **완전히 같아야** 한다 ―
    `value`뿐 아니라 `sources`·`priority_source`·`is_overwrite`까지. 그래서 비교를
    셀 dict 통째로 한다(값만 비교하면 provenance 오염을 놓친다).

    결함 주입 확인: `_resolve_one`의 첫 분기(왼쪽 값 우선)를 지우면 `L1.wafer_id`가
    `WF-RIGHT`로 바뀌어 dict 비교가 즉시 깨진다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-RIGHT",
                                  "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [
        # 왼쪽이 wafer_id 를 직접 실어 온 행 ― 조인 값과 다른 값이다
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01", "wafer_id": "WF-LEFT"},
        # 왼쪽이 비어 있는 행 ― 조인이 채워야 한다
        {"log_id": "L2", "core_lot": "LOT-A", "core_slot": "01"},
    ])

    # 기능 OFF(선언 파일이 없는 상태)에서의 페이로드가 기준선이다.
    vjc_path = vjc.VIRTUAL_JOIN_RULES_PATH
    try:
        vjc.VIRTUAL_JOIN_RULES_PATH = str(vjc_path) + ".absent"
        vjx.reset_cache()
        before = _payload(db)
    finally:
        vjc.VIRTUAL_JOIN_RULES_PATH = vjc_path
        vjx.reset_cache()
    after = _payload(db)

    assert before["L1"]["wafer_id"] == after["L1"]["wafer_id"], (
        "왼쪽 값이 있는 셀은 조인 전후로 바이트 단위 동일해야 한다")
    assert after["L1"]["wafer_id"]["value"] == "WF-LEFT"
    # 그리고 조인이 실제로 돌긴 했다 ― 비어 있던 형제 셀은 채워졌다.
    assert after["L2"]["wafer_id"]["value"] == "WF-RIGHT"
    assert before["L2"]["wafer_id"]["value"] in (None, "")


def test_blankness_means_what_it_means_everywhere_else(join_env, approved):
    """꼬리 공백은 값이 아니다 ― `crud.clean_str_value` 하나가 그 정의다.

    여기서만 `if not x`를 쓰면 `"  "`가 이 컬럼에서는 값이고 enrichment 큐에서는
    공백이 되어, 같은 셀이 두 화면에서 다르게 읽힌다.

    `_seed_raw`를 쓰는 이유는 위 헬퍼 docstring에 있다 ― 정규 쓰기 경로는 공백을 NULL로
    바꿔 버려서 이 축을 픽스처가 **활성화하지 못한다**(결함 주입에서 초록이었다).
    """
    db = join_env
    _seed_raw(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                      "core_slot": "01", "wafer_id": "WF-RIGHT",
                                      # 오른쪽 값이 공백뿐 ― 값이 아니다
                                      "fab_site": "   "}])
    _seed_raw(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "LOT-A",
                                    "core_slot": "01", "wafer_id": "   "}])
    cells = _payload(db)
    # 왼쪽이 공백뿐이면 "비었음" ― 조인 값이 이긴다
    assert cells["L1"]["wafer_id"]["value"] == "WF-RIGHT"
    # 오른쪽이 공백뿐이어도 "비었음" ― 미상이다
    assert cells["L1"]["fab_site"]["value"] == "미상"


def test_two_rules_on_one_column_do_not_depend_on_declaration_order(join_env, approved,
                                                                    tmp_path, monkeypatch):
    """같은 컬럼을 두 선언이 노출해도 답이 **선언 순서로 바뀌지 않는다.**

    규칙을 하나씩 적용하며 페이로드를 고쳐 나가면, 값을 못 찾은 첫 규칙이 써 놓은
    `미상`을 두 번째 규칙이 **"왼쪽에 값이 있다"로 오독**한다(absent-only 판정은 셀의
    현재 값을 보므로). 그러면 실제 값이 있는데도 영영 `미상`으로 남고, 두 선언의 순서만
    바꾸면 답이 달라진다. `attach`가 제안을 먼저 모으고 셀당 한 번만 결정하는 이유다.

    결함 주입 확인: `attach`를 규칙별 순차 적용으로 되돌리면 `dict`가 삽입 순서를
    보존하므로 `miss` 선언이 먼저 돌고 `L1.fab_site`가 `미상`으로 굳어 깨진다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-1",
                                  "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01",
                                "eqp_id": "NO-SUCH-KEY"}])
    # 같은 `fab_site`를 두 선언이 노출한다. 첫 번째는 절대 맞지 않는 키로 잇고
    # (항상 미상), 두 번째가 진짜 답을 갖는다.
    decls = {
        "miss": {"left_table": "vjx_test_log", "right_table": "vjx_test_wafer",
                 "join_key": [{"left": "eqp_id", "right": "core_lot"}],
                 "expose": ["fab_site"]},
        "hit": _decl(["fab_site"]),
    }
    p = tmp_path / "two_rules.json"
    p.write_text(json.dumps(decls), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    # 두 선언 모두 승인돼야 이 테스트가 의미를 갖는다(오른쪽이 같은 테이블이라
    # `approved` 대역이 둘 다 통과시킨다 ― 단일 컬럼 키는 UNIQUE 부분집합 규칙으로 통과).
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, columns: "uq_fake"
                        if table == "vjx_test_wafer" else None)
    vjx.reset_cache()
    assert len(vjx.rules_for(db, "vjx_test_log")) == 2

    assert _payload(db)["L1"]["fab_site"]["value"] == "M1", (
        "값을 못 찾은 선언이 먼저 돌았다고 해서 답이 미상이 되면 안 된다")


def test_neither_side_has_a_value_gives_the_label(join_env, approved):
    """왼쪽도 비고 오른쪽도 없으면 `unresolved_label`(사용자 확정 2026-07-31)."""
    db = join_env
    _seed(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "NO", "core_slot": "NO"}])
    cells = _payload(db)
    assert cells["L1"]["wafer_id"]["value"] == "미상"


def test_the_label_comes_from_the_rule_not_from_a_constant(join_env, approved,
                                                           tmp_path, monkeypatch):
    """라벨은 선언의 `unresolved_label`이다 ― 하드코딩된 `미상`이 아니다."""
    db = join_env
    p = tmp_path / "custom_label.json"
    p.write_text(json.dumps({"vjx_rule": _decl(["fab_site"], unresolved_label="UNKNOWN")}),
                 encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    vjx.reset_cache()
    _seed(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "NO", "core_slot": "NO"}])
    assert _payload(db)["L1"]["fab_site"]["value"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# provenance ― 쓰지 않고 말한다
# ---------------------------------------------------------------------------

def test_a_joined_cell_carries_its_source_in_the_existing_channel(join_env, approved):
    """조인이 만든 셀은 `sources`/`priority_source`에 `virtual_join`을 싣는다.

    `cell_sources`가 쓰는 것과 **같은 어휘**라 기존 셀 소스 표시가 새 코드 없이 읽는다.
    합쳐진 컬럼(`wafer_id`)에서 어느 셀이 왼쪽 값이고 어느 셀이 조인 값인지 구분하는
    유일한 수단이므로, 이것이 없으면 shadow 거부가 막던 오독이 그대로 돌아온다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-RIGHT",
                                  "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01", "wafer_id": "WF-LEFT"},
        {"log_id": "L2", "core_lot": "LOT-A", "core_slot": "01"},
    ])
    cells = _payload(db)

    # 조인이 채운 셀 ― 출처가 보인다
    assert cells["L2"]["wafer_id"]["priority_source"] == vjx.SOURCE_NAME
    assert cells["L2"]["wafer_id"]["sources"][vjx.SOURCE_NAME] == "WF-RIGHT"
    # 왼쪽 값이 이긴 셀 ― 조인은 흔적을 남기지 않는다(관여했지만 졌다)
    assert vjx.SOURCE_NAME not in cells["L1"]["wafer_id"]["sources"]
    assert cells["L1"]["wafer_id"]["priority_source"] != vjx.SOURCE_NAME


def test_the_label_cell_also_says_the_join_is_why(join_env, approved):
    """`미상`도 조인의 답이다 ― 출처 없이 두면 저장된 공백과 구별되지 않는다."""
    db = join_env
    _seed(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "NO", "core_slot": "NO"}])
    cell = _payload(db)["L1"]["fab_site"]
    assert cell["value"] == "미상"
    assert cell["priority_source"] == vjx.SOURCE_NAME
    assert cell["sources"][vjx.SOURCE_NAME] is None, "조인은 봤고 아무것도 없었다"


def test_nothing_is_persisted_by_a_read(join_env, approved):
    """virtual join은 조회 시점 계산이다 ― `cell_sources`에 한 행도 쓰지 않는다.

    썼다면 `source_name='virtual_join'` 행이 남고, 그 순간 서열(`SOURCE_PRIORITY`
    미등재 → 99)과 철회 경로가 걸린 진짜 층이 되어 버린다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-1", "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"}])
    _payload(db)
    _payload(db)
    leaked = db.query(models.CellSource).filter(
        models.CellSource.source_name == vjx.SOURCE_NAME).count()
    assert leaked == 0
    assert vjx.SOURCE_NAME not in crud.SOURCE_PRIORITY, (
        "등재하면 기계 계산이 서열을 얻는다 ― enrichment 3종과 같은 논거")


# ---------------------------------------------------------------------------
# 쓰기 거부 ― 모든 진입점
# ---------------------------------------------------------------------------

def test_write_to_a_virtual_column_is_refused_at_the_crud_funnel(join_env, approved):
    """모든 쓰기 경로가 수렴하는 자리에서 거부된다 ― 거부의 구조적 근거."""
    db = join_env
    with pytest.raises(ValueError) as exc:
        _seed(db, "vjx_test_log", [{"log_id": "L1", "fab_site": "typed-by-hand"}])
    assert "fab_site" in str(exc.value)


@pytest.mark.parametrize("source_name,label", [
    ("user", "grid edit / paste"),
    ("pipeline_parser", "file ingestion"),
    ("chain_ingestion", "chain worker"),
])
def test_write_to_a_virtual_column_is_refused_for_every_writer(join_env, approved,
                                                               source_name, label):
    """거부는 **누가 쓰는지와 무관**하다 ― 컬럼이 없다는 사실은 소스별로 달라지지 않는다."""
    db = join_env
    with pytest.raises(ValueError):
        _seed(db, "vjx_test_log", [{"log_id": "L1", "fab_site": "x"}],
              source_name=source_name)


def test_write_to_a_virtual_column_is_refused_at_the_http_edit_endpoint(join_env, approved,
                                                                        client):
    """편집·붙여넣기·Push가 모두 타는 그 엔드포인트에서 400이 된다.

    셋은 서버에서 같은 요청이다(`PUT /tables/{t}/data/updates`) ― 클라이언트의 편집
    커밋(`api.js`), 붙여넣기(`clipboard.js`), 맵/DOE Push(`map_editor.js`)가 전부
    이 경로로 온다. 그래서 진입점 3개가 검사 1개로 덮인다.
    """
    db = join_env
    res = client.put("/tables/vjx_test_log/data/updates", json={
        "updates": [{"business_key_val": "L1", "updates": {"fab_site": "x"},
                     "source_name": "user", "updated_by": "tester"}]})
    assert res.status_code == 400
    assert "fab_site" in res.json()["detail"]
    # 그리고 아무것도 쓰이지 않았다 ― 거부는 부분 적용을 남기지 않는다.
    assert db.query(models.DYNAMIC_TABLES["vjx_test_log"]).count() == 0


def test_a_colliding_column_stays_writable(join_env, approved):
    """🔴 충돌 컬럼은 **거부하지 않는다.**

    `wafer_id`는 `vjx_test_log`에 실재하는 저장 컬럼이다. 막으면 사용자가 조인 값을
    고칠 방법이 사라진다 ― 그 쓰기가 곧 absent-only 규칙의 "왼쪽 값 있음"을 만든다.
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-RIGHT",
                                  "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"}])
    assert _payload(db)["L1"]["wafer_id"]["value"] == "WF-RIGHT"

    # 사용자가 조인 값을 고친다 ― 거부되지 않고, 그 뒤로는 왼쪽 값이 이긴다.
    _seed(db, "vjx_test_log", [{"log_id": "L1", "wafer_id": "WF-CORRECTED"}],
          source_name="user")
    cell = _payload(db)["L1"]["wafer_id"]
    assert cell["value"] == "WF-CORRECTED"
    assert vjx.SOURCE_NAME not in cell["sources"]


def test_the_write_core_still_drops_it_even_if_the_guard_is_bypassed(join_env, approved):
    """관문 뒤의 두 번째 층 ― 코어 자신도 가상 컬럼을 저장하지 않는다.

    관문(`refuse_virtual_join_columns`)은 **말해 주는** 층이다. 그것을 우회해 코어를
    직접 불러도 미선언 컬럼 드롭이 남아 있어야 `cell_sources`에 행이 생기지 않는다.

    이것이 중요한 이유는 파급 때문이다: `delete_cell_source_batch`와
    `set_cell_manual_priority_batch`는 컬럼에 **직접 `setattr`** 하는 유일한 다른 두
    곳인데, 둘 다 **이미 존재하는 `CellSource` 층**에만 작동한다. 가상 컬럼으로는
    그 층이 만들어질 수 없으므로 두 경로가 구조적으로 도달 불가능해진다 ―
    그 논거 전체가 이 테스트 한 줄 위에 서 있다.
    """
    db = join_env
    crud.apply_row_update_internal(db, "vjx_test_log", schemas.GeneralUpdateItem(
        business_key_val="L1", updates={"log_id": "L1", "fab_site": "sneaked-in"},
        source_name="user", updated_by="test"))
    db.flush()
    assert db.query(models.CellSource).filter(
        models.CellSource.table_name == "vjx_test_log",
        models.CellSource.column_name == "fab_site").count() == 0, (
        "가상 컬럼에 소스 층이 생기면 Pin/철회 경로가 그것에 도달할 수 있게 된다")


def test_the_refusal_does_not_depend_on_a_call_site_remembering_it(join_env, approved):
    """거부가 **구조적**이라는 주장의 근거: 쓰기 코어의 호출부가 하나다.

    `apply_row_update_internal`을 부르는 곳이 `apply_batch_updates` 하나뿐이라,
    그 함수 앞에 선 관문을 우회해 컬럼에 도달할 쓰기 경로가 존재하지 않는다.
    호출부가 늘어나면 이 테스트가 그것을 알린다.
    """
    import inspect
    src = inspect.getsource(crud)
    calls = [ln for ln in src.splitlines()
             if "apply_row_update_internal(" in ln and not ln.strip().startswith("def ")]
    assert len(calls) == 1, (
        f"쓰기 코어의 호출부가 {len(calls)}개다 ― 관문을 우회하는 경로가 생겼는지 "
        f"확인하고, 정당하면 그 호출부도 refuse_virtual_join_columns 뒤로 보낼 것")


# ---------------------------------------------------------------------------
# 가드 존중 ― 승인되지 않은 선언은 조인을 만들지 않는다
# ---------------------------------------------------------------------------

def test_an_unverified_declaration_produces_no_join_at_all(join_env):
    """🔴 `approved` 대역이 **없는** 유일한 테스트다.

    UNIQUE 인덱스가 없으면(= sqlite라 `unique_index_covering`이 None) 선언은 승인되지
    않고, 승인되지 않은 선언은 **한 컬럼도 붙이지 않는다.** 실행기가
    `load_virtual_join_rules`(모양만)를 소비하도록 바꾸면 이 테스트가 빨개진다 ―
    그 차이가 실측 1억 3천만 행이다.

    쓰기 거부도 같이 사라져야 한다: 승인되지 않았으면 `fab_site`는 그냥 존재하지 않는
    컬럼이고, 기존의 미선언 컬럼 드롭이 그것을 맡는다(가상 컬럼 거부가 아니다).
    """
    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-1", "fab_site": "M1"}])
    _seed(db, "vjx_test_log", [{"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"}])

    assert vjx.rules_for(db, "vjx_test_log") == []
    assert vjx.virtual_only_columns(db, "vjx_test_log") == set()
    cells = _payload(db)
    assert "fab_site" not in cells["L1"], "승인 없이 컬럼이 붙었다"
    assert cells["L1"]["wafer_id"]["value"] in (None, ""), "승인 없이 값이 채워졌다"


def test_a_declaration_without_a_unique_index_is_named_in_the_refusal(join_env):
    """거부는 운영자에게 **할 일을 준다** ― 만들어야 할 인덱스의 DDL."""
    db = join_env
    rejections = []
    rules = vjc.load_verified_rules(db, known_tables=crud.TABLE_CONFIG,
                                    rejections=rejections)
    assert rules == []
    named = [r for r in rejections if r.get("code") == vjc.CODE_NO_UNIQUE_INDEX]
    assert len(named) == 1
    assert "vjx_test_wafer" in named[0]["facts"]["required_index_ddl"]


# ---------------------------------------------------------------------------
# 비용 ― 행당이 아니라 페이지당
# ---------------------------------------------------------------------------

def test_the_join_costs_one_query_per_rule_per_page_not_per_row(join_env, approved):
    """🔴 N+1이면 이 테스트가 빨개진다 ― 왼쪽 테이블은 1,000만 행이 될 수 있다.

    행 수를 3배로 늘려도 조인이 발행하는 SELECT 수는 **변하지 않아야** 한다. 절대값이
    아니라 **행 수에 대한 불변성**을 재는 이유는, 절대값은 무관한 리팩터링에도 흔들려
    금방 꺼지는 테스트가 되기 때문이다.
    """
    from sqlalchemy import event

    db = join_env
    _seed(db, "vjx_test_wafer", [{"wafer_key": "K1", "core_lot": "LOT-A",
                                  "core_slot": "01", "wafer_id": "WF-1", "fab_site": "M1"}])

    def _count_for(n_rows):
        _seed(db, "vjx_test_log", [{"log_id": f"N{n_rows}_{i}", "core_lot": "LOT-A",
                                    "core_slot": "01"} for i in range(n_rows)])
        model = models.DYNAMIC_TABLES["vjx_test_log"]
        row_ids = [r.row_id for r in db.query(model).all()]
        rule = vjx.rules_for(db, "vjx_test_log")[0]
        seen = []
        bind = db.get_bind()

        def _on_exec(conn, cursor, statement, *a, **k):
            seen.append(statement)
        event.listen(bind, "before_cursor_execute", _on_exec)
        try:
            vjx.execute_rule(db, rule, row_ids)
        finally:
            event.remove(bind, "before_cursor_execute", _on_exec)
        return len(seen), len(row_ids)

    q_small, n_small = _count_for(5)
    q_large, n_large = _count_for(20)

    assert n_large > n_small, "픽스처가 실제로 행을 늘리지 않았다"
    assert q_small == q_large == 1, (
        f"조인이 행 수에 따라 질의를 늘린다: {n_small}행={q_small}회, "
        f"{n_large}행={q_large}회 (N+1)")


def test_chunking_keeps_the_in_list_bounded(join_env, approved):
    """`row_id IN (...)`은 1000개씩 끊는다 ― 시스템 공통 규율."""
    db = join_env
    rule = _decl(["fab_site"])
    normalized = vjc.validate_virtual_join_rules({"r": rule},
                                                 known_tables=crud.TABLE_CONFIG)[0]
    from sqlalchemy import event
    _seed(db, "vjx_test_log", [{"log_id": f"C{i}", "core_lot": "LOT-A",
                                "core_slot": "01"} for i in range(7)])
    model = models.DYNAMIC_TABLES["vjx_test_log"]
    row_ids = [r.row_id for r in db.query(model).all()]

    seen = []
    bind = db.get_bind()

    def _on_exec(conn, cursor, statement, *a, **k):
        seen.append(statement)
    event.listen(bind, "before_cursor_execute", _on_exec)
    try:
        vjx.execute_rule(db, normalized, row_ids, chunk_size=3)
    finally:
        event.remove(bind, "before_cursor_execute", _on_exec)
    assert len(seen) == 3, "7행 / 청크 3 = 3회여야 한다"


def test_a_table_with_no_declaration_pays_nothing(join_env, approved):
    """선언이 없는 테이블은 조인 질의를 한 번도 발행하지 않는다."""
    db = join_env
    from sqlalchemy import event
    seen = []
    bind = db.get_bind()

    def _on_exec(conn, cursor, statement, *a, **k):
        if "vjx_test_wafer" in statement:
            seen.append(statement)
    # 캐시를 먼저 데운다(선언 로드 자체는 테이블당이 아니라 프로세스당이다)
    vjx.rules_for(db, "vjx_test_wafer")
    event.listen(bind, "before_cursor_execute", _on_exec)
    try:
        assert vjx.attach(db, "vjx_test_wafer", [{"row_id": "x", "data": {}}]) == 0
    finally:
        event.remove(bind, "before_cursor_execute", _on_exec)
    assert seen == []
