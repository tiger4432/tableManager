"""Virtual join 실행기 ― 선언을 **LEFT 조인 한 방**으로 바꾸고 행 페이로드에 붙인다.

`virtual_join_config`는 선언만 다룬다("조인 실행은 여기 없다"). 여기가 그 실행이다.
계약은 그 파일의 모듈 docstring이 정본이고, 이 파일은 그것을 **지키는 쪽**이다.

[입구는 하나다 ― `load_verified_rules`]
모양만 통과한 선언(`load_virtual_join_rules`)을 실행하면 유일성이 검사되지 않은 조인이
돌고, 그 차이가 실측 1억 3천만 행이다. 그래서 이 파일은 `load_verified_rules`만 부른다.
유일성은 이 파일의 책임이 아니라 **가드의 책임**이고, 가드를 우회하는 경로를 두지 않는
것이 이 파일이 그 책임을 존중하는 방식이다.

[질의 모양 ― 페이지당 규칙당 1회. 행당이 아니다]
    SELECT l.row_id, r.row_id, r.<expose...>
      FROM <left> l LEFT OUTER JOIN <right> r ON l.k1 = r.k1 AND ...
     WHERE l.row_id IN (:이미 가져온 페이지의 row_id들)
이미 페이징된 `row_id` 목록으로 좁히므로 왼쪽 스캔이 없고, 오른쪽은 승인 조건이었던
**UNIQUE 인덱스**를 그대로 탄다. 오른쪽이 조인 키로 유일하니 출력 행 수 = 입력 행 수다
(팬아웃 없음 ― 그것이 가드가 보장한 바로 그 성질이다). `row_id IN (...)`은 1000개씩
끊는다(`CHUNK_SIZE` ― 시스템 공통 규율).

🔴 **INNER는 금지다.** `outerjoin`만 쓴다. INNER면 오른쪽이 없는 왼쪽 행이 **조용히
사라져** 페이지에서 행이 증발한다.

[미상은 두 경우를 덮는다 ― 여기가 그 두 번째가 사는 곳]
평범한 LEFT 조인은 ①(오른쪽 행 없음)만 준다. ②(행은 있는데 값이 빔)는 SQL이 값을
그대로 돌려주므로 **파이썬에서 걸러야** 한다. 실측이 그 이유다 ―
`bonding_log → core_wafer_map.wafer_id`는 14,436행 전부가 오른쪽 행을 찾지만 26.27%가
빈 값이다. ②를 빼면 그 26%가 「값이 있다」로 읽힌다. `_resolve_one`이 그 한 줄이고,
빈 판정은 `crud.clean_str_value(v) == ""` ― 시스템의 나머지와 **같은 뜻**이라야 한다.

`matched`(오른쪽 행이 실제로 있었는가)를 따로 들고 다니는 이유는 표시가 아니라
**관측 가능성**이다. ①과 ②가 같은 `미상`으로 접히고 나면 ②를 지웠을 때 아무 테스트도
빨개지지 않는다 ― 두 분기가 따로 보여야 회귀가 잡힌다.

[충돌 컬럼 ― absent-only. `enrichment_candidates`와 같은 연산이다]
왼쪽에 같은 이름이 이미 있는 expose 컬럼은 **부재일 때만** 채운다(사용자 확정
2026-07-31). 왼쪽 값이 있는 셀은 **한 바이트도 건드리지 않는다** ― 조인 값을 버린다.
이것은 `enrichment_candidates`의 absent-only 관문과 구조적으로 같은 연산이라 같은
어휘(`blank` / `clean_str_value(v) == ""`)를 쓴다. 다른 철자를 만들지 않는다.

⚠️ 코드까지 재사용하지는 못했고 그 이유는 하나다: 그쪽 관문은 **`cell_sources`에
provenance가 있는가**를 묻는다(쓰기 전 검사라 영속 흔적이 답이다). 이쪽은 아무것도
쓰지 않으므로 물을 provenance가 없고, 답은 **표시값이 비었는가**뿐이다. 실제로
`AutoConfirmCollector.flush`도 그 표시값 판정만은 같은 한 줄(`clean_str_value(v) == ""`)을
직접 쓴다 ― 재사용한 것은 그 줄이고, 재사용하지 못한 것은 그 위의 영속 조회다.

[provenance ― 쓰지 않고 말한다]
합쳐진 컬럼은 셀마다 출처가 다르다(왼쪽 값 / 조인 값 / 미상). 그것이 보이지 않으면
`미상`이 막으려던 바로 그 오독이 컬럼 안에서 다시 일어난다. 그래서 조인이 만든 셀은
`sources`에 `virtual_join`을 달고 `priority_source`를 그것으로 세운다 ― `cell_sources`가
쓰는 것과 **같은 어휘**라 기존 셀 소스 표시가 그대로 읽는다(새 UI 0).

🔴 **`cell_sources`에 쓰지 않는다.** virtual join은 조회 시점 계산이고 아무것도 영속하지
않는다. 페이로드 안에서만 사는 소스다.
🔴 **`crud.SOURCE_PRIORITY`에 등록하지 않는다** ― `enrichment_auto_confirm` 3종과 같은
논거다. 등록하지 않으면 서열 99(최하위)라 `user`(0)를 이길 수 없고, 애초에 이 이름으로는
`CellSource` 행이 만들어지지 않으므로 `compute_priority_value`에 도달할 경로도 없다.

[쓰기 거부 ― `virtual_only`에만 건다]
`virtual_only` 컬럼(왼쪽에 실재하지 않는 것)은 저장 컬럼이 아니다. 거기로 가는 쓰기는
없는 컬럼을 겨냥한다. 거부는 `crud.apply_batch_updates` **한 곳**에 있다 ― 모든 쓰기
경로(API 편집·붙여넣기·Push·인제션·체인·enrichment·재생)가 그 함수로 수렴하므로 새
호출부가 검사를 잊을 자리가 없다.
`collide` 컬럼은 반대로 **써야 한다**. 실재하는 저장 컬럼이고, 그 쓰기가 곧 absent-only
규칙의 "왼쪽 값 있음"을 만든다 ― 막으면 사용자가 조인 값을 고칠 방법이 사라진다.
"""
import logging
import time

logger = logging.getLogger("VirtualJoinExecutor")

# 셀 소스 어휘. `cell_sources.source_name`이 쓰는 것과 같은 문자열 공간이다 ―
# 클라이언트의 셀 소스 목록이 새 코드 없이 이것을 읽는다.
SOURCE_NAME = "virtual_join"

# `row_id IN (...)` 청킹 상수. 시스템 공통(enrichment_candidates.CHUNK_SIZE와 같은 값).
CHUNK_SIZE = 1000

# 승인된 선언 캐시의 수명(초). 캐시가 필요한 이유는 이 조회가 **모든 쓰기 배치**에도
# 걸리기 때문이다(쓰기 거부가 여기서 컬럼 목록을 얻는다).
#
# 영구 캐시는 핫리로드를 죽이고, 매번 재조회는 선언 파일 읽기 + 규칙당 `pg_index` 질의를
# 배치마다 반복한다. 그 사이가 이 상수다 ― `main.TABLE_COUNT_CACHE`(5초)와 같은 규율.
# 명시적 무효화(`reset_cache`)가 웹서버 리로드 경로에 걸려 있고, TTL은 그 훅이 없는
# 워커 프로세스를 위한 뒷받침이다.
RULES_CACHE_TTL = 5.0

_RULES_CACHE = {"at": 0.0, "by_left": None}

# THE emptiness predicate and THE payload renderer, bound once instead of per cell.
# They are `crud.clean_str_value` / `crud.resolved_text_value` and nothing else - the
# point of hoisting them is speed, NOT a second spelling of either rule.
_CLEAN = None
_RENDER = None


def _bind_crud():
    """Bind the two `crud` functions the per-cell path uses. Lazy: `crud` imports this
    module, so a module-scope import would be a cycle."""
    global _CLEAN, _RENDER
    from database import crud
    _CLEAN = crud.clean_str_value
    _RENDER = crud.resolved_text_value


def reset_cache():
    """승인 선언 캐시를 즉시 버린다. config 리로드 경로가 부른다."""
    _RULES_CACHE["at"] = 0.0
    _RULES_CACHE["by_left"] = None


def _verified_by_left_table(db) -> dict:
    """`{왼쪽 테이블: [승인된 선언, ...]}`. TTL 캐시.

    **`load_verified_rules`만 부른다.** 모양만 통과한 선언은 유일성이 검사되지 않았고,
    그것을 실행하면 가드가 존재하지 않는 것과 같다.
    """
    now = time.time()
    cached = _RULES_CACHE["by_left"]
    if cached is not None and (now - _RULES_CACHE["at"]) < RULES_CACHE_TTL:
        return cached

    import virtual_join_config as vjc
    from database import crud

    by_left = {}
    try:
        for rule in vjc.load_verified_rules(db, known_tables=crud.TABLE_CONFIG):
            by_left.setdefault(rule["left_table"], []).append(rule)
    except Exception as e:
        # 선언을 읽지 못하면 **조인이 없는 상태**로 간다(빈 dict). 그것이 안전한 방향이다
        # ― 붙지 않은 컬럼은 눈에 보이는 부재고, 잘못 붙은 컬럼은 조용한 오답이다.
        logger.error("[VirtualJoin] verified rules unavailable, NO join is in effect: %s", e)
        by_left = {}

    _RULES_CACHE["by_left"] = by_left
    _RULES_CACHE["at"] = now
    return by_left


def rules_for(db, left_table: str) -> list:
    """`left_table`에 걸린 **승인된** 선언들."""
    return list(_verified_by_left_table(db).get(left_table) or [])


def join_onclause(left_model, right_model, rule: dict):
    """조인 ON 절 ― 표기 정규화가 걸린 키는 **양쪽 다** 접는다.

    🔴 **이 함수가 ON 절의 유일한 철자다.** `execute_rule`(페이로드용 실행)과
    `resolved_expression`(WHERE에 들어가는 식)이 각자 `==`를 쓰고 있었고, 접기가 한쪽에만
    들어가면 같은 조인이 두 경로에서 **다른 행 집합**을 낸다 ― 그리드에 보이는 값과
    필터가 세는 행이 어긋나는, 조용한 오답의 교과서적 모양이다.

    🔴 **한쪽만 접을 수 있는 인자가 없다.** 접기 규칙은 선언 시점에
    `notation_norm.join_pair_rules`가 「어느 한쪽이라도 선언됐으면 양쪽」으로 결정해
    `pair["fold"]` 하나에 실어 두었고, 여기서는 그 하나를 양쪽에 똑같이 적용할 뿐이다.
    실측(2026-08-04): `dt_log.core_lot`은 병합군 15개, `core_wafer_map.core_lot`은 0개다.
    깨끗한 쪽에 선언할 이유가 있는 운영자는 없고, 한쪽만 접힌 조인은 **이미 맞고 있던
    매치를 조용히 잃는다**.
    """
    from sqlalchemy import and_
    import notation_norm

    parts = []
    for p in rule["join_key"]:
        left_col = getattr(left_model, p["left"])
        right_col = getattr(right_model, p["right"])
        fold = p.get("fold")
        if fold:
            left_col = notation_norm.fold_notation_sql(left_col, fold)
            right_col = notation_norm.fold_notation_sql(right_col, fold)
        parts.append(left_col == right_col)
    return and_(*parts)


def virtual_only_columns(db, left_table: str) -> set:
    """이 테이블에서 **저장 컬럼이 아닌** expose 컬럼 이름들 ― 쓰기 거부의 대상.

    `collide`(왼쪽에 실재하는 컬럼)는 포함하지 않는다. 그쪽은 평범한 저장 컬럼이라
    쓰기가 정상이고, 그 쓰기가 absent-only 규칙의 "왼쪽 값 있음"을 만든다.
    """
    out = set()
    for rule in rules_for(db, left_table):
        # `virtual_only`가 None이면 table_config 없이 검증된 선언이라 어느 쪽인지
        # 모른다. 실행기의 입구는 항상 table_config를 주므로 정상 경로에선 발생하지
        # 않지만, 모를 때 **거부하지 않는 쪽**으로 기울면 없는 컬럼에 쓰기를 허용하게
        # 되므로 expose 전체를 대상으로 본다(모르면 막는다).
        vo = rule.get("virtual_only")
        out.update(rule["expose"] if vo is None else vo)
    return out


def announced_columns(db, left_table: str) -> list:
    """`/schema`가 이 테이블에 **덧붙여 알리는** 컬럼들. 항목 하나가 컬럼 하나다:
    `{"name", "type", "editable": False, "right_table", "rule", "unresolved_label"}`.

    [왜 있는가 ― 알리지 않은 컬럼은 그리드가 그리지 못한다]
    페이로드는 이미 조인 컬럼을 싣고 있었지만 `/schema`가 그것을 말하지 않아
    `virtual_only` 컬럼은 **화면에 나타나지 않았다**. 노출을 선언한 운영자에게 컬럼도
    사유도 주지 않는 것은 「효력 없이 조용한 설정」과 같은 종류의 결함이다.

    [`virtual_only`만 알린다 ― `collide`는 이미 스키마에 있다]
    `collide` 컬럼은 왼쪽의 **실재하는 저장 컬럼**이다. 조인이 부재일 때만 채울 뿐,
    컬럼 자체는 `table_config`가 선언했고 `/schema`가 이미 싣는다. 여기서 한 번 더
    실으면 같은 컬럼이 두 번 알려지고, "이 컬럼은 저장되는가"를 스키마로 판정하는
    소비자가 한 응답에서 두 답을 받는다. 그래서 **collide만 있는 선언은 스키마 응답을
    한 바이트도 바꾸지 않는다**(`test_schema_virtual_columns`가 본문을 통째로 비교한다).

    [`attach`가 만드는 집합과 같아야 한다 ― 둘의 유일한 출처가 `rules_for`인 이유]
    이 목록은 "행 페이로드에 새로 생길 컬럼"의 **선언**이다. `attach`가 만드는 집합과
    어긋나면 지금 고치는 그 결함이 방향만 바꿔 되돌아온다(알렸는데 값이 없는 컬럼 /
    값이 있는데 안 알린 컬럼). 그래서 둘 다 `rules_for` 하나에서 파생되고, 같은 이름을
    두 선언이 노출할 때의 라벨도 `attach`의 `labels.setdefault`와 같이 **먼저 온 선언이
    이긴다** ― 알리는 라벨과 실제로 셀에 앉는 라벨이 달라선 안 된다.

    [`virtual_only`가 None이면 아무것도 알리지 않는다 ― 쓰기 거부와 **반대 방향**이다]
    None은 "어느 expose가 왼쪽에 실재하는지 모른다"는 뜻이다. 쓰기 거부는 그때 expose
    전체를 막는다(모르면 막는다 ― 없는 컬럼에 쓰기가 가는 것이 더 나쁘다). 알림에서
    같은 자세를 취하면 실재하는 collide 컬럼을 **두 번 알리게** 되므로 안전한 방향이
    반대다: 모르면 알리지 않는다. 잃는 것은 알림뿐이고(눈에 보이는 부재), 그때도 쓰기는
    여전히 막혀 있다.

    🔴 **이 목록은 쓰기를 막지 않는다.** 막는 것은 `crud.refuse_virtual_join_columns`
    하나이고 그것이 모든 쓰기 경로가 수렴하는 깔때기에 앉아 있다. `editable: False`는
    클라이언트가 **편집을 제안하지 않게** 하는 표시일 뿐이라, 그 표시를 지워도 쓰기는
    여전히 400이다(테스트가 그 독립성을 따로 고정한다).
    """
    from database import crud

    out, seen = [], set()
    for rule in rules_for(db, left_table):
        vo = rule.get("virtual_only")
        if vo is None:
            continue
        right_types = (crud.TABLE_CONFIG.get(rule["right_table"]) or {}).get("column_types") or {}
        for col in vo:                      # `expose` 순서를 그대로 물려받은 목록이다
            if col in seen:
                continue                    # 먼저 온 선언이 이긴다 ― `attach`와 같은 규칙
            seen.add(col)
            out.append({
                "name": col,
                # 타입은 **오른쪽 테이블의 선언**이다. 값이 거기서 오기 때문이다.
                # ⚠️ 값의 정의역에는 `unresolved_label`(문자열)도 들어간다 ― 그래서
                # 숫자 컬럼이 숫자가 아닌 값을 실을 수 있고, 그 사실을 클라이언트가 알 수
                # 있도록 라벨을 같이 싣는다.
                "type": right_types.get(col, "string"),
                # 이 표시는 **편집을 제안하지 말라**는 뜻이지 금지의 근거가 아니다
                # (금지는 `crud.refuse_virtual_join_columns`). 항상 False인 이유는
                # 이 목록이 저장 컬럼이 아닌 것만 담기 때문이다 ― True가 될 수 있는
                # 항목은 애초에 이 목록에 들어오지 못한다.
                "editable": False,
                # 「고치려면 어디로 가야 하는가」의 답. 쓰기 거부 메시지는 "조인 원본
                # 테이블에서 수정하세요"라고만 말하고 그 테이블을 지목하지 못한다.
                "right_table": rule["right_table"],
                # 「이 컬럼은 어느 선언이 만들었는가」 ― `/admin/config/virtual-join/verify`가
                # 선언 이름으로 답을 들고 있으므로, 이 이름이 그 화면으로 가는 다리다.
                "rule": rule["name"],
                # 라벨은 선언마다 다르다. 클라이언트가 「미상」을 하드코딩하지 않고
                # 이 값을 읽어야 설정이 실제로 효력을 갖는다.
                "unresolved_label": rule["unresolved_label"],
            })
    return out


KIND_COLLIDE = "collide"
KIND_VIRTUAL_ONLY = "virtual_only"


def resolved_column_announcements(db, left_table: str) -> list:
    """Every column whose displayed value this server RESOLVES THROUGH A JOIN, with the
    facts a client needs to act on it. `/schema` publishes this as `join_resolved_columns`.

    Entry: `{"name", "kind", "rule", "right_table", "unresolved_label"}`.

    [Why this exists next to `announced_columns` rather than inside it]
    They answer different questions and the difference is the whole defect:
      `announced_columns`  - "what columns must /schema ADD to the column list?"
                             virtual_only ONLY. A collide column is already in `columns`,
                             and announcing it twice would give two answers to
                             "is this column stored?".
      this function        - "which columns' values come from a join?"
                             collide AND virtual_only.
    A collide column is a REAL stored column that a join also fills, so it looks perfectly
    ordinary to the grid - and then its Blank filter matches nothing, because the value the
    operator sees COALESCEs to a non-empty label. The client cannot know that without being
    told, and it must not deduce it by differencing `columns` against `virtual_columns`:
    that set arithmetic is wrong for the collide case BY CONSTRUCTION.

    🔴 **`kind` is STATED, never derived.** The client asking "not in virtual_columns,
    therefore stored-and-plain" is exactly the inference this key exists to replace.

    🔴 **`unresolved_label` rides PER ENTRY** because it is per declaration. Two rules on
    one table legitimately carry different labels, so a client that hardcodes `미상` must
    be provably wrong - and `virtual_join_config.DEFAULT_UNRESOLVED_LABEL` is only a
    default, not the value.

    🔴 **THIS IS NOT THE WRITE GUARD, and it must never become one.** The refusal is
    `crud.refuse_virtual_join_columns`, on the funnel every write path converges on. This
    key only stops the UI PROPOSING an edit that would come back 400. A defence living in
    a READ response is no defence at all - any client that never calls `/schema` would
    write freely. `test_join_resolved_columns.py` asserts, structurally and behaviourally,
    that suppressing this announcement does not make a write succeed.

    Note there is no writability field: editability already lives in `columns[].editable`
    (collide) and `virtual_columns[].editable: false` (virtual_only). Repeating it here
    would be a second source of truth for one fact, and the two would drift.

    Verified declarations only (`rules_for`), never `load_virtual_join_rules` - announcing
    an unverified declaration would promise a join the guard refuses to run.
    """
    out, seen = [], set()
    for rule in rules_for(db, left_table):
        # `virtual_only` is None only when the rule was validated without table_config,
        # which `rules_for` never does. If it ever happens, treat every exposed column as
        # virtual_only rather than guessing it is stored.
        vo = rule.get("virtual_only")
        virtual_only = set(rule["expose"] if vo is None else vo)
        for col in rule["expose"]:
            if col in seen:
                continue        # first declaration wins - same rule as `attach`'s labels
            seen.add(col)
            out.append({
                "name": col,
                "kind": KIND_VIRTUAL_ONLY if col in virtual_only else KIND_COLLIDE,
                "rule": rule["name"],
                "right_table": rule["right_table"],
                "unresolved_label": rule["unresolved_label"],
            })
    return out


def exposed_columns(db, left_table: str) -> set:
    """Every column name a verified join contributes to this table - collide AND
    virtual_only.

    Derived from `resolved_column_announcements` ON PURPOSE, so `/schema`'s
    `join_resolved_columns` and the set the search path actually resolves cannot disagree.
    If a client greys a column the server will not resolve - or resolves one it never
    announced - the two have drifted, and deriving one from the other removes the place
    that drift could live.
    """
    return {e["name"] for e in resolved_column_announcements(db, left_table)}


def resolved_expression(db, left_model, left_table: str, col_name: str, query):
    """SQL for the value a user SEES in `col_name`, plus the query that can evaluate it.

    Returns `(query, expr, label)`; `(query, None, None)` when no verified join exposes
    this column. `query` comes back with one LEFT OUTER JOIN added per contributing rule.

    [Why a join and not a correlated subquery]
    This expression goes in WHERE, so it is evaluated against the whole left table, not
    against one page. A correlated scalar subquery would be one index probe PER LEFT ROW
    - 10 million of them on a 10-million-row table. A LEFT JOIN lets the planner choose a
    hash or merge join and read the right side once.

    🔴 **The join cannot change the row count, and that is not an assumption.** The right
    side is unique on the join key because `virtual_join_config` refuses to verify a
    declaration that lacks a UNIQUE index covering it. That is what keeps `query.count()`
    honest and keyset pagination undisturbed - and it is why this may only ever be built
    from `rules_for` (verified), never from `load_virtual_join_rules` (shape only).

    [The expression is `attach`'s rule, translated - not a second rule]
    `attach` takes the left value if non-empty, else the first non-empty joined value in
    rule order, else the label. `COALESCE` is that same "first non-null wins", and
    `crud.blank_to_null` is what turns "non-empty" into "non-null" using the ONE
    emptiness declaration both sides share. The label comes from the first rule exposing
    the column, matching `attach`'s `labels.setdefault` and `announced_columns`.

    🔴 **No `trim()` appears here.** It does not need to: `crud.normalize_stored_text`
    makes storage canonical at the write boundary, so blank-in-SQL and blank-in-Python
    are the same set. Adding a trim here would silently re-introduce the second spelling.

    [EVERY part renders to text BEFORE the COALESCE - board items N7 / N8]
    The label is a string, so the whole expression is a TEXT expression, and a part that
    is not text kills the read. N7 (2026-08-02) fixed that for `number`; N8 (2026-08-04)
    established it is a property of the COALESCE, not of numbers - a `datetime` expose
    column died with `InvalidDatetimeFormat` and a `boolean` one with
    `InvalidTextRepresentation`, both measured on the production dialect, both the same
    defect wearing a different type.

    The rendering therefore goes through ONE funnel, `crud.column_text_sql`, which asks
    "is this already text?" rather than "is this one of the types we know about" - so a
    type nobody has thought of yet gets a CAST instead of a 500. The canonical spelling
    of each family, and the Python twin that has to agree with it in the payload, live
    in `crud` beside that funnel.
    """
    from sqlalchemy.orm import aliased
    from sqlalchemy import func
    from database import crud, models

    rules = [r for r in rules_for(db, left_table) if col_name in r["expose"]]
    if not rules:
        return query, None, None

    def _text_part(col):
        # The MODEL type decides, not table_config - a column that physically exists
        # answers for itself. (A `column_types` entry naming a metadata column, e.g.
        # `created_at`, is skipped by the model builder and resolves to the metadata
        # DateTime/Boolean; asking the model is what makes that case come out right.)
        return crud.column_text_sql(col)

    parts = []
    # The left column participates only when it actually exists on the left table -
    # i.e. a `collide` column. For a `virtual_only` column there is nothing to prefer.
    left_cols = (crud.TABLE_CONFIG.get(left_table) or {}).get("column_types") or {}
    if col_name in left_cols and hasattr(left_model, col_name):
        parts.append(_text_part(getattr(left_model, col_name)))

    for rule in rules:
        right_model = models.DYNAMIC_TABLES.get(rule["right_table"])
        if right_model is None:
            continue
        # Aliased per rule: two declarations may name the same right table, and an
        # unaliased second join would collide on the table name.
        right = aliased(right_model)
        # ONE spelling of the ON clause (`join_onclause`), shared with `execute_rule`.
        # A notation-folded key MUST fold identically here or the WHERE-side row set
        # and the payload-side row set disagree.
        onclause = join_onclause(left_model, right, rule)
        # 🔴 outerjoin, never inner - an inner join here would DELETE left rows that have
        # no right match from the result, which is the population capability (1) is for.
        query = query.outerjoin(right, onclause)
        parts.append(_text_part(getattr(right, col_name)))

    if not parts:
        return query, None, None

    label = rules[0]["unresolved_label"]
    return query, func.coalesce(*parts, label), label


# ---------------------------------------------------------------------------
# 실행 ― LEFT 조인 한 방
# ---------------------------------------------------------------------------

def execute_rule(db, rule: dict, row_ids: list, chunk_size: int = CHUNK_SIZE) -> dict:
    """선언 1건을 주어진 왼쪽 row_id들에 대해 실행한다.

    반환: `{row_id: {"matched": bool, "values": {expose_col: 오른쪽 원값}}}`.
    조인 결과에 나타나지 않은 row_id는 dict에 없다(왼쪽 행 자체가 없는 경우뿐이다 ―
    LEFT 조인이라 오른쪽이 없어도 왼쪽 행은 항상 나온다).

    `matched`는 **표시에 쓰지 않는다** ― `attach`는 읽지 않는다. 두 소비자가 있다:
      ① 테스트. ①(오른쪽 행 없음)과 ②(행은 있는데 빈 값)가 같은 `미상`으로 접히고
         나면 ②를 지워도 아무 테스트가 빨개지지 않는다. 이 필드가 그 두 분기를 따로
         관측 가능하게 만드는 유일한 수단이다(실제로 처음엔 없어서 헛통과했다).
      ② 이 계약 위에 올라올 레인들. 「웨이퍼 기록이 없다」와 「기록은 있는데 id가
         비었다」는 정렬·필터·내보내기에서 **다른 답**이고, 그 구별은 조인 시점에만
         알 수 있다 ― 페이로드까지 내려온 `미상` 문자열에서는 복원할 수 없다.
    두 소비자 다 없어지면 이 필드도 같이 걷어야 한다(보는 이 없는 필드는 다음 사람에게
    "무언가 검사되고 있다"는 착각을 준다 ― `virtual_join_config` 상단의 그 규율이다).
    """
    from database import models

    left = models.DYNAMIC_TABLES.get(rule["left_table"])
    right = models.DYNAMIC_TABLES.get(rule["right_table"])
    if left is None or right is None or not row_ids:
        return {}

    onclause = join_onclause(left, right, rule)
    # 🔴 THE LIST IS CHECKED BEFORE THE SELECT IS BUILT, NOT CAUGHT WHILE IT RUNS. A name
    # the right model does not carry makes `getattr` below raise, and that one name used to
    # take the whole rule with it - every sibling column omitted for a fault that belongs
    # to one of them. A column absent because a NEIGHBOUR is broken renders exactly like a
    # column that is empty, which is the least visible failure this codebase has.
    #
    # 🔴 A LIST CHECK AND NOT A TRY PER COLUMN, deliberately: wrapping each column would
    # mean building and running the SELECT once per column to find out which one throws,
    # and the cost of this seam would change. Everything needed is knowable before
    # execution, because what throws is the ATTRIBUTE LOOKUP while composing the query.
    # So the query count is exactly what it was - one per chunk, whatever gets dropped.
    #
    # `hasattr` is the exact twin of the `getattr` on the next line rather than a stricter
    # imitation of it. For these models the two agree in any case: `init_dynamic_models`
    # gives a dynamic class nothing but Columns, so "has the attribute" and "is a column of
    # the table" cannot disagree here.
    #
    # HOW A DECLARED NAME GOES MISSING (measured 2026-09-03): `virtual_join_config`
    # validates `expose` against the right table's `column_types` KEYS, and the model
    # builder SKIPS the graph-sync metadata names - which a table created after
    # 2026-08-31 no longer receives. So the declaration is valid and the column is not
    # there, and neither side is wrong.
    declared = list(rule["expose"])
    expose = [c for c in declared if hasattr(right, c)]
    if len(expose) != len(declared):
        for name in declared:
            if name in expose:
                continue
            logger.error(
                "[VirtualJoin] rule '%s': '%s' is declared in expose but '%s' has no such "
                "column - that ONE column is omitted; the rule's other columns (%s) are "
                "unaffected",
                rule["name"], name, rule["right_table"], expose or "none")
    # 오른쪽 `row_id`는 표시 대상이 아니라 **①/②를 가르는 유일한 증거**다.
    # 오른쪽 expose 값이 NULL이면 "행이 없었다"인지 "행은 있었고 값이 NULL이었다"인지
    # 값만 봐서는 구별할 수 없다.
    cols = [left.row_id, right.row_id] + [getattr(right, c) for c in expose]

    out = {}
    for i in range(0, len(row_ids), chunk_size):
        chunk = row_ids[i:i + chunk_size]
        rows = (db.query(*cols)
                .select_from(left)
                .outerjoin(right, onclause)   # 🔴 INNER 금지 ― 왼쪽 행이 증발한다
                .filter(left.row_id.in_(chunk))
                .all())
        for row in rows:
            left_row_id, right_row_id = row[0], row[1]
            out[left_row_id] = {
                "matched": right_row_id is not None,
                "values": {c: v for c, v in zip(expose, row[2:])},
            }
    return out


def _resolve_one(joined_value, left_value, has_left_column: bool, label: str) -> tuple:
    """셀 하나의 최종 값과 출처. 반환 `(value, from_join: bool)`.

    absent-only 규칙 그대로다(사용자 확정 2026-07-31):
        왼쪽 값 있음  → 왼쪽 값 그대로, 조인 값은 버린다  (from_join=False)
        왼쪽 값 비었음 → 조인 값                          (from_join=True)
        둘 다 없음    → `label`                          (from_join=True)

    `미상`이 두 경우를 덮는 자리가 바로 여기다 ― `clean_str_value(joined) == ""`는
    ①(오른쪽 행이 없어 NULL)과 ②(행은 있는데 빈 문자열)를 **한 줄로** 같이 잡는다.
    `is None`만 보면 ②가 빈 문자열 그대로 새어 나가 「값이 있다」로 읽힌다(실측 26.27%).

    [The joined value is rendered through `crud.resolved_text_value` - board item N8]
    The SQL half of this seam (`resolved_expression`) spells a temporal or boolean value
    with a PINNED text format. If the payload carried the raw value instead, the grid
    would paint FastAPI's `.isoformat()` (whose offset follows the DB session timezone)
    while a filter compared the pinned UTC text, and "search for what you see" would have
    two answers. Rendering here makes the two halves the same string by construction.
    Numbers deliberately stay raw - see `crud.resolved_text_value`.

    ⚠️ The LEFT value is returned untouched, because a cell the join LOST must be
    byte-identical to what it would be without this feature. For a `collide` column of a
    pinned-text type that leaves one measured divergence (payload isoformat vs SQL
    canonical text) on left-owned cells only; no such declaration exists today and
    closing it is a Lead PM call (it needs a declaration-time refusal).

    [Why the two `crud` functions are module globals and not a local import]
    This is called once PER CELL - 40,000 times for a 10,000-row page with four exposed
    columns - and `from database import crud` on every one of those is a `sys.modules`
    round trip buying nothing. The import stays LAZY (bound on first use) because
    `crud` imports this module back; binding it at module scope is an import cycle.
    """
    if _CLEAN is None:
        _bind_crud()
    if has_left_column and _CLEAN(left_value) != "":
        return left_value, False
    if _CLEAN(joined_value) != "":
        return _RENDER(joined_value), True
    return label, True


def attach(db, table_name: str, data_list: list) -> int:
    """행 페이로드 목록에 승인된 조인의 expose 컬럼을 붙인다. 붙인 셀 수를 돌려준다.

    `data_list`는 `main.fetch_and_merge_metadata`가 만든 `[{row_id, data:{col: 셀}}]`.
    셀 모양(`{value, is_overwrite, sources, ...}`)은 그 함수가 정본이고 여기서는
    **같은 키 집합**을 채운다 ― 조인 컬럼만 모양이 다르면 클라가 분기해야 한다.
    """
    if not data_list:
        return 0
    rules = rules_for(db, table_name)
    if not rules:
        return 0
    if _CLEAN is None:
        _bind_crud()
    clean, render = _CLEAN, _RENDER

    row_ids = [d.get("row_id") for d in data_list if d.get("row_id")]

    # 🔴 **모든 규칙을 먼저 모으고, 셀마다 한 번만 결정한다.** 규칙을 하나씩 적용하며
    # 페이로드를 고쳐 나가면 앞 규칙이 쓴 `미상`을 뒤 규칙이 **왼쪽 값으로 오독**해서
    # (absent-only 판정은 "지금 셀에 값이 있는가"를 보므로) 영영 채우지 못한다.
    # 같은 컬럼을 두 선언이 노출하는 구성에서 규칙 순서가 답을 바꾸는 결함이 된다.
    #
    # 그래서 제안(proposal)만 모은다: 한 셀에 대해 **처음으로 비어 있지 않은 조인 값**이
    # 이긴다. 아무 규칙도 값을 주지 못하면 그때 라벨로 떨어진다.
    # 🔴 **`(row_id, col)` 튜플 키를 쓰지 않는다** ― 컬럼별로 한 겹 판다.
    # 튜플 키는 셀마다 튜플을 **두 번** 만든다(적재 때 한 번, 조회 때 또 한 번). 실측
    # 10,000행 x 4컬럼에서 80,000개다. 컬럼당 dict 한 개면 조회는 `by_row.get(rid)`라
    # 아무것도 만들지 않는다. 뜻은 그대로다: 같은 (행, 컬럼)에 대해 처음으로 비어 있지
    # 않은 조인 값이 이긴다.
    proposals = {}          # col -> {row_id: 조인이 준 원값(비어 있을 수 있음)}
    labels = {}             # col -> 그 컬럼을 노출한 첫 선언의 unresolved_label
    # 🔴 THE COLLECT STEP FAILS PER RULE, AND THAT IS THE WHOLE OF THIS GUARD. One rule
    # that cannot be built used to take EVERY exposed column of this table down with it:
    # `main.py`'s outer `try` wraps the entire call, so the failure skipped the decide step
    # too and columns belonging to perfectly healthy rules simply were not there. Measured
    # 2026-09-03 - three tests in `test_virtual_join_types` were red about `event_at` and
    # `stamp_at`, neither of which had anything wrong with it, purely because a fourth
    # column in the same declaration could not be built.
    #
    # That vanishing renders EXACTLY like "this cell has no value", which is the failure
    # this repo keeps meeting: a column absent because somebody ELSE broke looks the same
    # as a column that is genuinely empty.
    #
    # 🔴 IT GOES HERE AND NOT AROUND THE DECIDE STEP BELOW. The "collect everything, then
    # decide once per cell" shape is deliberate - deciding rule by rule lets a later rule
    # read an earlier rule's 미상 as a LEFT value, which makes rule ORDER change the answer.
    # Wrapping the decision would run it on partial proposals and reintroduce exactly that.
    # A rule that raises contributes ZERO proposals, and at the decision a rule with no
    # proposals is indistinguishable from a rule whose proposals were all empty: neither
    # wins. So the direction the outer handler documents - an absent column beats a wrong
    # one - is preserved, and it is preserved for that rule ALONE.
    #
    # Verified rather than assumed: the only statement here that can raise in practice is
    # `execute_rule`, which builds the SELECT (`getattr(right, c)` on a column the model
    # does not have). It raises BEFORE anything is merged, so "zero proposals" is exact
    # and not approximate.
    for rule in rules:
        try:
            joined = execute_rule(db, rule, row_ids)
        except Exception as exc:                                        # noqa: BLE001
            # 🔴 THE RULE'S NAME, because the outer handler only ever said the TABLE's and
            # an operator reading "columns omitted on dt_log" could not tell which of the
            # declarations was the broken one.
            logger.error(
                "[VirtualJoin] rule '%s' could not be built on '%s'; its columns %s are "
                "omitted and every OTHER rule's columns are unaffected: %s",
                # `name` is REQUIRED by `VerifiedJoinDescriptor` - a fallback here
                # would be a reserved value nothing can produce, which is how a dead
                # branch starts looking like a handled case.
                rule["name"], table_name, list(rule["expose"]), exc)
            continue
        label = rule["unresolved_label"]
        for col in rule["expose"]:
            labels.setdefault(col, label)
            by_row = proposals.setdefault(col, {})
            for rid, hit in joined.items():
                # `prev is None`은 「키가 없다」와 「값이 None이다」를 한꺼번에 덮는데,
                # 그래도 되는 이유는 두 경우의 처리가 **같기** 때문이다 ― 값이 None이면
                # `clean(None) == ""`라 어차피 덮어쓴다. 한 규칙 안에서 각 (행,컬럼)은
                # 한 번만 지나가므로 이 비교는 언제나 **앞선 규칙**의 값과의 비교다.
                prev = by_row.get(rid)
                if prev is not None and clean(prev) != "":
                    continue        # 이미 실한 값이 있다 ― 먼저 온 것이 이긴다
                by_row[rid] = hit["values"].get(col)

    # 🔴 **바깥이 행, 안이 컬럼이다**(종전 반대). 페이로드 키 순서는 그대로다 ― 한 행
    # 안에서 컬럼은 여전히 `labels` 순서로 삽입되므로 직렬화 바이트가 바뀌지 않는다.
    # 바뀌는 것은 `entry.get(...)`을 **행당 1회**만 한다는 것뿐이다(종전엔 컬럼 수만큼).
    label_items = list(labels.items())
    touched = 0
    for entry in data_list:
        r_data = entry.get("data")
        if not isinstance(r_data, dict):
            continue
        rid = entry.get("row_id")

        for col, label in label_items:
            joined_value = proposals[col].get(rid)
            cell = r_data.get(col)
            has_left_column = isinstance(cell, dict)
            left_value = cell.get("value") if has_left_column else None

            value, from_join = _resolve_one(joined_value, left_value,
                                            has_left_column, label)
            if not from_join:
                # 왼쪽 값이 이긴 셀은 **아무것도 바꾸지 않는다.** 페이로드가 이 기능
                # 도입 전과 바이트 단위로 같아야 한다 ― `sources`에 흔적을 남기는
                # 것조차 "조인이 관여했다"는 거짓말이다(관여했지만 졌다).
                continue

            # 셀 단위 provenance. `cell_sources`와 **같은 어휘**라 기존 표시가 그대로
            # 읽는다. 값이 `label`이면 소스 값은 조인이 실제로 돌려준 것(없거나 빈 값)
            # 이라 "조인은 봤고 아무것도 없었다"가 그대로 읽힌다.
            # Same rendering as the cell value: a source entry spelled differently from
            # the value it explains would send a reader looking for a second story.
            rendered = render(joined_value)

            if has_left_column:
                srcs = cell.get("sources")
                srcs = dict(srcs) if isinstance(srcs, dict) else {}
                srcs[SOURCE_NAME] = rendered
                cell["value"] = value
                cell["sources"] = srcs
                cell["priority_source"] = SOURCE_NAME
                # `is_overwrite`는 **표시값**에 대한 파생 표식이다("지금 보이는 이 값이
                # 사람이 덮어쓴 값인가"). 이 분기의 표시값은 조인이 준 것이므로 False다.
                # 사람이 남긴 층 자체는 지워지지 않는다 ― 위에서 기존 `sources`를 복사해
                # 유지하므로 `user` 층이 있었다면 그대로 보인다(기록은 `sources`가,
                # 표식은 이 플래그가 나른다).
                cell["is_overwrite"] = False
            else:
                # 왼쪽에 셀이 없던 `virtual_only` 컬럼. 종전엔 **빈 셀을 만든 뒤 네 키를
                # 덮어썼고**, `sources`는 방금 만든 `{}`를 또 `dict()`로 복사했다 ― 셀마다
                # dict 3개. 최종 상태를 그대로 쓰면 2개다. 키 삽입 순서는 종전 리터럴과
                # 같으므로(덮어쓰기는 순서를 바꾸지 않는다) JSON 바이트가 동일하다.
                r_data[col] = {"value": value, "is_overwrite": False,
                               "is_collision_merge": False,
                               "sources": {SOURCE_NAME: rendered},
                               "updated_by": "system",
                               "manual_priority_source": None,
                               "priority_source": SOURCE_NAME}
            touched += 1
    return touched
