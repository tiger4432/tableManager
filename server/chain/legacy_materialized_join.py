# -*- coding: utf-8 -*-
"""⚠️ THE SECOND WRITE-JOIN DOOR, AND IT IS A DEBT (S-283 · 판정 461 ③).

🔴 THE RULED DOOR IS `chain/join_into.py`. The owner's ruling (2026-09-16) is that a join
writes its columns INTO THE TABLE and that `into.table` is the way to say so. This module is
the OTHER one: the engine a legacy `materialize: true` declaration runs on. It exists here
for one reason - deleting it would kill joins that are running today (판정 452 ①) - and it
lives only as long as such declarations do.

⛔ SO IT IS NOT `join_into`'S PEER, AND THE NAME SAYS SO. Two modules that both write a
join are 「같은 기능에 두 경로」, which `join_into`'s own docstring already named as a cost it
was taking on knowingly. Nothing new should be built against this module; a declaration
that wants to write a join is written as `into: {table: …}` and goes through the ruled one.

🔴 AND THE KEY CANNOT BE ALLOWED TO DIVERGE. Both doors fold the join key through
`notation_norm`, and the unique index is built from the same expression (S-181, S-245) - so
two spellings of a key would not merely disagree, they would make PostgreSQL stop using the
index while every test stayed green. That shared fold is what makes two doors survivable
until this one closes.

⚰️ MOVED OUT OF `virtual_join/executor.py`, WHICH HELD BOTH HALVES. The read-time half -
the one that answered a SELECT with columns that were never stored - retired with the
capability; this is the half that writes. The split was taken by dependency closure from
the write entry points: everything here was reachable from them, and nothing here was
reachable only from the read side.
"""
import logging
import time

from chain import cell_layer
from verified_join_contract import usable_expose


logger = logging.getLogger("VirtualJoinExecutor")

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

_RULES_CACHE = {"at": 0.0, "by_left": None, "by_right": None}

def reset_cache():
    """승인 선언 캐시를 즉시 버린다. config 리로드 경로가 부른다."""
    _RULES_CACHE["at"] = 0.0
    _RULES_CACHE["by_left"] = None
    _RULES_CACHE["by_right"] = None

def _verified_by_left_table(db) -> dict:
    """`{왼쪽 테이블: [승인된 선언, ...]}`. TTL 캐시.

    **`load_verified_rules`만 부른다.** 모양만 통과한 선언은 유일성이 검사되지 않았고,
    그것을 실행하면 가드가 존재하지 않는 것과 같다.
    """
    now = time.time()
    cached = _RULES_CACHE["by_left"]
    if cached is not None and (now - _RULES_CACHE["at"]) < RULES_CACHE_TTL:
        return cached

    from chain import legacy_join_declaration as vjc
    from database import crud

    # 🔴 NOT THE READER'S SESSION (2026-09-15, outage five). Verifying every declaration
    # ran catalog SQL - and, since yesterday, an index probe - on the session of whoever
    # happened to miss the cache. One declaration on table B raising left the transaction
    # of a read of table A aborted, and nothing here rolled it back: the operator's own
    # words were 「내가 건드리던 테이블과 완전 다른 건데 왜 튀어나와서 막았던 거야」. The
    # verification now runs on its own session and closes it; a failure there can not
    # touch the read that asked. The reader only ever reads memory.
    from database.database import SessionLocal
    own = SessionLocal()
    by_left, by_right = {}, {}
    try:
        for rule in vjc.load_verified_rules(own, known_tables=crud.TABLE_CONFIG):
            by_left.setdefault(rule["left_table"], []).append(rule)
            by_right.setdefault(rule["right_table"], []).append(rule)
    except Exception as e:
        # 선언을 읽지 못하면 **조인이 없는 상태**로 간다(빈 dict). 그것이 안전한 방향이다
        # ― 붙지 않은 컬럼은 눈에 보이는 부재고, 잘못 붙은 컬럼은 조용한 오답이다.
        logger.error("[VirtualJoin] verified rules unavailable, NO join is in effect: %s", e)
        by_left, by_right = {}, {}
    finally:
        try:
            own.rollback()
            own.close()
        except Exception:
            pass

    _RULES_CACHE["by_left"] = by_left
    _RULES_CACHE["by_right"] = by_right
    _RULES_CACHE["at"] = now
    return by_left

def rules_for(db, left_table: str) -> list:
    """`left_table`에 걸린 **승인된** 선언들."""
    return list(_verified_by_left_table(db).get(left_table) or [])

def rules_for_right(db, right_table: str) -> list:
    """`right_table`이 **오른쪽**인 승인된 선언들 ― 이 표가 «지고 있는 유일성» (S-174).

    🔴 **승인된 것만이다. 그것이 이 방향의 핵심이다.** 승인은 「조인 키를 덮는 UNIQUE
    인덱스가 «실제로» 있다」는 뜻이고, 인덱스가 없으면 깨질 제약도 없다. 모양만 통과한
    선언으로 행을 거절하면 데이터베이스가 받아 줬을 행을 «가드가» 버린다.

    같은 캐시·같은 한 번의 로드다(`by_left`와 «한 패스»에서 나온다) ― 쓰기 경로가
    선언 파일을 배치마다 다시 읽지 않는다.
    """
    _verified_by_left_table(db)
    return list((_RULES_CACHE["by_right"] or {}).get(right_table) or [])

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
        # 🔴 NULL EQUALS NULL WHERE KEYS ARE COMPARED (S-181, 판정 285). `==` is SQL's
        # rule and SQL's rule is the opposite one: a NULL key matched nothing, including
        # another NULL, so a join on a partly-empty key silently returned no row rather
        # than the row an operator could see was there.
        #
        # ⚠️ AND IT IS `coalesce` ON BOTH SIDES BECAUSE THE INDEX IS THAT SHAPE. The
        # required unique index is `coalesce(col, '')` (`index_key_expression`), and
        # PostgreSQL uses an expression index only when the query's expression MATCHES it
        # — a mismatch here does not fail, it quietly turns a join into a sequential scan.
        # `IS NOT DISTINCT FROM` would answer the same question and would NOT match the
        # index, which is why the coalesce spelling is the one used on both sides.
        # 🔴 [S-245] AND THE CAST IS PART OF THAT SHAPE NOW. `coalesce(col, '')` is a
        # text sentence, and on a `number` key PostgreSQL answered this very clause with
        # 「invalid input syntax for type double precision: ""」 - so the pair in
        # `notation_norm` folds the TYPE too, and the index DDL asks the same function.
        parts.append(notation_norm.key_expression_sql(left_col, fold)
                     == notation_norm.key_expression_sql(right_col, fold))
    return and_(*parts)

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
    expose, _missing = usable_expose(rule, right, "the row payload")
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
                # 🔴 [S-280 · 판정 434] THE ROW THAT ANSWERED, KEPT RATHER THAN THROWN AWAY.
                # This SELECT has always fetched `right.row_id` - it is what `matched` is
                # computed from, one line up - and then dropped it. It is exactly the note
                # a retraction needs once that row is deleted, so it costs nothing to keep
                # and nothing new to fetch.
                "origin_row_id": right_row_id,
                "values": {c: v for c, v in zip(expose, row[2:])},
            }
    return out

def materialize_rows(db, rule: dict, row_ids: list) -> dict:
    """Write the join's answer onto the named left rows, as the RULE's own layer.

    Returns `{"rule", "written", "refusal"}`.

    🔴 `source_name` IS THE RULE NAME, and that is what makes a manual edit win. Layering
    already ranks a `user` overwrite above a named source, so nothing here has to defend the
    operator's edit -- and nothing here may, because a second precedence rule would be a
    second answer to 「who wins」.

    ⚠️ A ROW THE JOIN DID NOT MATCH IS SKIPPED, NOT WRITTEN BLANK. Writing `None` would be
    this repository's 「없는 것」 / 「0인 것」 defect: an absent right-hand row and a right-hand
    row holding an empty value would land identically, and the layer could never be told
    apart from a real value later.
    """
    from database import crud, schemas

    if not rule.get("materialize"):
        return {"rule": rule.get("name"), "written": 0,
                "refusal": "rule '%s' does not declare materialize" % rule.get("name")}

    results = execute_rule(db, rule, list(row_ids))
    expose = list(rule.get("expose") or ())
    items = []
    for row_id, answer in results.items():
        answer = answer or {}
        values = answer.get("values") or {}
        # 🔴 「null 로 쓰면 null 이 되어야 한다」(소유자 2026-09-15). 종전에는 오른쪽 값이
        #    None 이면 그 칸을 «빼고» 썼고, 전부 None 이면 행을 통째로 건너뛰었다 — 그래서
        #    「오른쪽 기록이 null 이다」라는 사실이 «아무 데도 안 남았다».
        #    ⚠️ 그렇다고 «안 맞은 행»에 null 을 쓰지는 않는다. 그건 「값이 null 이다」라는
        #    «다른 주장»이고, 이 저장소가 「없는 것/0인 것」이라 부르는 바로 그 병이다.
        #    두 경우를 가르는 것이 `matched` 이고, 그 필드는 «그러라고» 있다(execute_rule 계약).
        if not answer.get("matched"):
            continue
        cells = {col: values.get(col) for col in expose}
        if not cells:
            continue
        items.append(schemas.GeneralUpdateItem(
            row_id=row_id, updates=cells,
            source_name=rule["name"], updated_by=rule["name"],
            # 🔴 [S-280 · 판정 434] WHICH REFERENCE ROW THIS ANSWER CAME FROM. Only ever
            # set on a MATCHED row - the `continue` above already left the unmatched ones
            # unwritten, so there is no path here that stamps a cell with the absence of
            # a row.
            origin_row_id=answer.get("origin_row_id")))
    if not items:
        return {"rule": rule["name"], "written": 0, "refusal": None}

    crud.apply_batch_updates(db, rule["left_table"],
                             schemas.GeneralUpdateBatch(updates=items))
    return {"rule": rule["name"], "written": len(items), "refusal": None}

def on_target_rows_changed(db, rule: dict, row_ids: list) -> dict:
    """Trigger ⓐ — the TARGET row moved, so only that row is rewritten. Cost is O(rows).

    ⚠️ NO CEILING APPLIES HERE, deliberately. The ceiling exists because ONE reference row
    can fan out to many target rows; a target row costs itself, and refusing that would
    refuse an ordinary edit.
    """
    return materialize_rows(db, rule, row_ids)

def on_reference_rows_changed(db, rule: dict, key_values: list) -> dict:
    """Trigger ⓑ — a REFERENCE row moved, so every target row carrying that key follows.

    🔴 THIS IS THE EXPENSIVE ONE AND IT COUNTS BEFORE IT WRITES (판정 302). Measured on this
    box: one `dt_job` covers 70,800 rows of `dt_log`, about 92 seconds of writing at the
    owner's IO spec. Counting first is what lets the rule's declared ceiling refuse the whole
    thing instead of discovering the cost halfway through.

    ⛔ OVER THE CEILING WRITES NOTHING. Not the first N rows: a table left part new and part
    old says nothing about which row is which.
    """
    from chain import legacy_join_declaration as vjc

    counted = vjc.rewrite_row_count(db.connection(), rule, key_values)
    refusal = vjc.rewrite_refusal(rule, counted)
    if refusal:
        return {"rule": rule["name"], "written": 0, "counted": counted, "refusal": refusal}

    row_ids = _left_row_ids_for_key(db, rule, key_values)
    result = materialize_rows(db, rule, row_ids)
    result["counted"] = counted
    return result

def _left_row_ids_for_key(db, rule: dict, key_values: list) -> list:
    """Which target rows carry this join key — folded the SAME way the counter folds it."""
    from sqlalchemy import text

    from chain import legacy_join_declaration as vjc
    from database.crud import fold_key_value

    left_columns = [p["left"] for p in rule["join_key"]]
    folds = vjc._folds_list(rule["right_columns"], rule.get("right_folds"))
    where = " AND ".join(
        "%s = :k%d" % (vjc.index_key_expression(col, fold, rule["left_table"]), i)
        for i, (col, fold) in enumerate(zip(left_columns, folds)))

    def _bound(col, value):
        folded = fold_key_value(rule["left_table"], col, value)
        return "" if folded is None else folded

    params = {("k%d" % i): _bound(col, value)
              for i, (col, value) in enumerate(zip(left_columns, key_values))}
    sql = 'SELECT row_id FROM "%s" WHERE %s' % (rule["left_table"], where)
    return [row[0] for row in db.connection().execute(text(sql), params).fetchall()]

def retract_rows(db, rule: dict, row_ids, apply, columns=None) -> dict:
    """The named target rows lost their reference row, so this rule's layer on them goes.

    🔴 [S-280 · 판정 433 ③] `row_ids` AND `apply` ARE REQUIRED, AND THAT IS THE REPAIR.
    This function passed neither, and `withdraw_source` defaults both: `row_ids=None` means
    the WHOLE table and `apply=False` means a dry run that rolls back. So a function named
    `retract_rows` would have written nothing, and on the day somebody passed `apply` it
    would have taken every row instead of the ones that lost their source. Defaults are
    invisible at the call site — the same reason 판정 431 took the author default off the
    deletion doors — so there are none here and an omission is a TypeError at the boundary.

    ⚠️ THIS IS NOT THE ROUTE A DELETION TAKES. A deleted row is withdrawn by its own stamp
    (`cell_layer.withdraw_by_origin`, S-280), which needs no rule at all and serves the
    kinds a join key cannot reach. This one stays for a caller that already knows both the
    rule and the target rows.

    Nothing is written in the withdrawn cells' place: 「투영은 지워도 기록은 안 된다」, and
    inventing a `0` or a blank where a value used to be is how a screen stops being able to
    tell absence from measurement.

    🪦 It lived in `chain_replay` and was imported HERE, inside this function - the last seam
    of a four-module ring (S-211 ①, 판정 358). Retraction is not replay's behaviour; it is an
    operation both of us use, so it moved below both.
    """
    return cell_layer.withdraw_source(db, rule["left_table"], rule["name"],
                                      columns=list(columns or rule.get("expose") or ()),
                                      row_ids=list(row_ids), apply=apply)
