# -*- coding: utf-8 -*-
"""정렬 이름은 «해석되거나 거절된다» — 조용히 버려지지 않는다 (A-6).

[닫는 결함]
`GET /tables/{t}/data` 는 `order_by` 를 받고, `updated_at`·`id` 두 이름 «밖»의 모든 값을
`else: row_id.asc()` 로 떨어뜨렸다. 오타든 실존 사용자 컬럼이든 «같은 답»을 받았고,
응답에는 그 사실을 말하는 칸이 없다. 그래서 화면은 정렬된 줄 안다 —
**전수 최댓값이 아니라 «첫 페이지의 최댓값»이 맨 위에 서고, 기호는 전수 정렬과 같다.**
표가 한 페이지에 다 들어오면 옳게 보인다. 갈리는 것은 「다 로드됐나」 하나다.

[그래서 픽스처가 페이지 경계를 «넘는다»]
25행 · `limit=10`. `dt_lot` 값을 행 순서와 «어긋나게» 심어, ASC 도 DESC 도 row_id 순서의
첫 값과 다르다 — 한 방향만 재면 종전 동작이 절반은 초록으로 통과한다.

[격리] 접두 `a6_test_` — 사용자 gitignored config 에 실존할 수 없다.
[승인 대역] sqlite 라 `unique_index_covering` 이 항상 None 이다. 대역이 없으면 조인이
0건이고 가상 컬럼 시험이 «헛통과»한다 — `test_virtual_column_search.py` 와 같은 이유.
"""
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

ROWS = 25
LIMIT = 10

#: 행 순서(row_id)와 «어긋나는» 값. gcd(7,25)=1 이라 치환이고, 앞 10행이 담는 값의
#: 최소/최대(1 / 23)가 전수 최소/최대(0 / 24)와 «다르다» — 그 차이가 판별식이다.
DT_LOTS = ["L%02d" % ((i * 7 + 13) % ROWS) for i in range(ROWS)]

A6_TABLES = {
    "a6_test_row": {
        "business_key": "row_key",
        "column_types": {"row_key": "string", "dt_lot": "string",
                         "core_lot": "string", "core_slot": "string"},
        "display_columns": ["row_key", "dt_lot", "core_lot", "core_slot", "fab_site"],
    },
    "a6_test_ref": {
        "business_key": "ref_key",
        "column_types": {"ref_key": "string", "core_lot": "string",
                         "core_slot": "string", "fab_site": "string"},
        "display_columns": ["ref_key", "core_lot", "core_slot", "fab_site"],
    },
}

DECL = {
    "a6_rule": {
        "left_table": "a6_test_row", "right_table": "a6_test_ref",
        "join_key": [{"left": "core_lot", "right": "core_lot"},
                     {"left": "core_slot", "right": "core_slot"}],
        "expose": ["fab_site"],
    }
}


def _seed(db, table, rows):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name="pipeline_parser",
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id="seed_%s" % table, silent=True))


@pytest.fixture()
def env(db_session, client, tmp_path, monkeypatch):
    models.init_dynamic_models(A6_TABLES)
    crud.TABLE_CONFIG.update(A6_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    p = tmp_path / "virtual_join_rules.json"
    p.write_text(json.dumps(DECL), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, columns: "uq_fake"
                        if table == "a6_test_ref" else None)
    vjx.reset_cache()

    import main
    main.TABLE_COUNT_CACHE.clear()

    # `fab_site` 도 행 순서와 어긋나게 — 슬롯 i 의 사이트는 «뒤에서부터» 매긴다.
    _seed(db_session, "a6_test_ref",
          [{"ref_key": "R%02d" % i, "core_lot": "LOT-A", "core_slot": "%02d" % i,
            "fab_site": "S%02d" % (ROWS - 1 - i)} for i in range(ROWS)])
    _seed(db_session, "a6_test_row",
          [{"row_key": "K%02d" % i, "dt_lot": DT_LOTS[i],
            "core_lot": "LOT-A", "core_slot": "%02d" % i} for i in range(ROWS)])
    db_session.commit()
    yield client
    vjx.reset_cache()
    main.TABLE_COUNT_CACHE.clear()


def _page(client, **params):
    """응답 순서 그대로의 행 목록. 행 모양은 `{row_id, table_name, data: {col: {value}}}`."""
    params.setdefault("limit", LIMIT)
    r = client.get("/tables/a6_test_row/data", params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _vals(rows, col):
    return [r["data"][col]["value"] for r in rows]


def _refused(client, **params):
    params.setdefault("limit", LIMIT)
    return client.get("/tables/a6_test_row/data", params=params)


# ---------------------------------------------------------------------------
# ㉠ 모르는 이름은 «이름 대어» 거절한다
# ---------------------------------------------------------------------------

def test_an_undeclared_sort_name_is_refused_by_name(env):
    """조용한 기본값이 없다. 종전에는 오타가 `row_id.asc()` 를 받고 200 으로 나갔다."""
    res = _refused(env, order_by="no_such_column")
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert "no_such_column" in detail, detail
    assert "a6_test_row" in detail, detail
    # 운영자가 «어디에» 적어야 하는지가 문장 안에 있어야 한다.
    assert "table_config.json" in detail and "virtual_join_rules.json" in detail, detail


# ---------------------------------------------------------------------------
# ㉡ 선언된 컬럼은 «표 전체» 기준으로 정렬된다 — 페이지 경계를 넘어서
# ---------------------------------------------------------------------------

def test_a_declared_column_sorts_the_whole_table_not_the_first_page(env):
    """🔴 이 라운드의 판별식. 25행 중 «10행»만 받는데 답은 전수 순서여야 한다."""
    assert len(DT_LOTS) == ROWS and len(set(DT_LOTS)) == ROWS, "fixture lost its axis"
    page_one_by_row_id = DT_LOTS[:LIMIT]
    assert max(page_one_by_row_id) != max(DT_LOTS), "fixture lost its axis: DESC 판별 불가"
    assert min(page_one_by_row_id) != min(DT_LOTS), "fixture lost its axis: ASC 판별 불가"

    desc = _vals(_page(env, order_by="dt_lot", order_desc=True), "dt_lot")
    assert desc == sorted(DT_LOTS, reverse=True)[:LIMIT], desc
    asc = _vals(_page(env, order_by="dt_lot", order_desc=False), "dt_lot")
    assert asc == sorted(DT_LOTS)[:LIMIT], asc


# ---------------------------------------------------------------------------
# ㉢ 가상 조인 컬럼도 — 화면이 보여 주는 컬럼과 서버가 정렬하는 컬럼이 갈리면 안 된다
# ---------------------------------------------------------------------------

def test_a_virtual_join_column_sorts_through_the_binder(env):
    """`?filters=`·`?q=` 가 이미 지나는 그 자리를 정렬도 지난다.

    ⚰️ 종전 `test_no_sorting_was_added` 가 「정렬은 범위 밖」을 못 박고 있었다. 그 시험은
       행 «개수»만 셌기 때문에 정렬이 붙어도 초록이었다 — 못 박은 것이 없었다.
    """
    sites = ["S%02d" % (ROWS - 1 - i) for i in range(ROWS)]
    desc = _vals(_page(env, order_by="fab_site", order_desc=True), "fab_site")
    assert desc == sorted(sites, reverse=True)[:LIMIT], desc
    asc = _vals(_page(env, order_by="fab_site", order_desc=False), "fab_site")
    assert asc == sorted(sites)[:LIMIT], asc


# ---------------------------------------------------------------------------
# ㉣ 화면이 오늘 보내는 두 값은 «바이트 동일»
# ---------------------------------------------------------------------------

def test_the_screens_own_names_answer_exactly_as_before(env):
    """화면이 오늘 «보내는» 것은 바이트 동일이고, 못 보던 갈래는 열렸다.

    [판정 97] 화면은 sortLatest 가 꺼지면 `row_id&order_desc=false` 를, 켜지면
    `updated_at&true` 를 보낸다 — 그 둘은 이 라운드 앞뒤로 같다. 종전 `row_id` 는
    `order_desc` 를 «안 봤고», 그래서 머리글을 내림차순으로 눌러도 오름차순이 오면서
    기호만 내림차순였다 — A-6 의 판별식 문장과 «같은» 결함이다.
    """
    by_row_asc = _vals(_page(env, order_by="row_id", order_desc=False), "row_key")
    assert by_row_asc == ["K%02d" % i for i in range(LIMIT)], by_row_asc

    by_row_desc = _vals(_page(env, order_by="row_id", order_desc=True), "row_key")
    assert by_row_desc != by_row_asc, "row_id must now see order_desc"
    assert by_row_desc == ["K%02d" % i for i in range(ROWS - 1, ROWS - 1 - LIMIT, -1)],         by_row_desc

    up_asc = _vals(_page(env, order_by="updated_at", order_desc=False), "row_key")
    up_desc = _vals(_page(env, order_by="updated_at", order_desc=True), "row_key")
    assert len(up_asc) == LIMIT and len(up_desc) == LIMIT
    # 같은 초에 심겨 updated_at 이 동률이므로 tie-breaker(row_id)가 방향을 정한다 —
    # 그 tie-breaker 가 방향을 따라간다는 것이 종전 동작이고, 여기서 그것을 못 박는다.
    assert up_asc[0] == "K00" and up_desc[0] == "K%02d" % (ROWS - 1), (up_asc[0], up_desc[0])


# ---------------------------------------------------------------------------
# 점프는 정렬 «이름마다» 자기 비교식을 갖는다 — 없는 조합은 세지 않고 이름을 댄다
# ---------------------------------------------------------------------------

def test_a_jump_under_a_new_sort_is_refused_rather_than_answered_wrongly(env):
    """오프셋은 `updated_at`·`id`·`row_id` 세 이름에만 비교식이 있다.

    새 컬럼으로 정렬하는 동안 row_id 비교로 세면 «다른 순서»의 위치를 답하고, 점프는
    조용히 엉뚱한 페이지에 앉는다. 「없어서 0」이 아니라 「이름 대어 거절」이다.
    """
    rid = _page(env, order_by="row_id")[5]["row_id"]
    ok = _refused(env, order_by="row_id", target_row_id=rid)
    assert ok.status_code == 200 and ok.json()["target_offset"] == 5, ok.text
    # [판정 97] 오프셋도 방향을 «따라간다». 오름차순에서 6번째면 내림차순에서는
    # 끝에서 6번째다 — 안 따라가면 점프가 표의 반대편에 앉는다.
    rev = _refused(env, order_by="row_id", order_desc=True, target_row_id=rid)
    assert rev.status_code == 200 and rev.json()["target_offset"] == ROWS - 1 - 5, rev.text

    res = _refused(env, order_by="dt_lot", target_row_id=rid)
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert "target_row_id" in detail and "dt_lot" in detail, detail



# ---------------------------------------------------------------------------
# A-6-c  빈 값은 «어느 방향이든» 뒤로
#
# 🔴 「위냐 아래냐」의 취향이 아니다. 빈 칸은 값의 «부재»이므로 값들의 «어느 끝»에도 속하지
# 않는다 — 뒤다. 종전에는 PostgreSQL 이 오름차순에서 NULL 을 앞에 놓고 내림차순에서도 앞에
# 놓아서, 반쯤 채워진 컬럼을 정렬한 운영자는 «어느 화살표를 눌러도» 빈 행 한 페이지를 먼저
# 만났다. 찾던 행은 2 페이지에 있었다.
# ---------------------------------------------------------------------------

def _push(env, rows):
    """Add rows through the same door the grid uses - the fixture owns `db_session`."""
    res = env.put("/tables/a6_test_row/data/updates", json={
        "updates": [{"updates": dict(r), "source_name": "pipeline_parser",
                     "updated_by": "tester"} for r in rows]})
    assert res.status_code == 200, res.text


def _tail_value(env, order_desc):
    """The LAST `dt_lot` on the page, which is where a blank has to be."""
    rows = _page(env, order_by="dt_lot", order_desc=order_desc, limit=200)
    return _vals(rows, "dt_lot")[-1]


def test_a_blank_value_sorts_last_ascending(env):
    _push(env, [{"row_key": "BLANK_A", "core_lot": "L", "core_slot": "1"}])

    assert _tail_value(env, "false") in ("", None), (
        "a blank must come after every value ascending")


def test_a_blank_value_sorts_last_descending_too(env):
    """The half that makes it a RULE rather than a direction. If "last" held only one
    way, the other arrow would still open on a page of blanks."""
    _push(env, [{"row_key": "BLANK_D", "core_lot": "L", "core_slot": "1"}])

    assert _tail_value(env, "true") in ("", None), (
        "a blank must come after every value descending too")


def test_a_table_with_no_blank_value_is_ordered_exactly_as_before(env):
    """바이트 동일 대조. 이 규칙은 «빈 값이 있을 때만» 무언가를 바꾼다 — 없으면 종전 순서다.
    (이 픽스처의 25행에는 빈 `dt_lot` 이 없다.)"""
    up = _vals(_page(env, order_by="dt_lot", order_desc="false", limit=200), "dt_lot")
    down = _vals(_page(env, order_by="dt_lot", order_desc="true", limit=200), "dt_lot")

    assert up == sorted(up)
    assert down == sorted(down, reverse=True)
