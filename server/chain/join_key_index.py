# -*- coding: utf-8 -*-
"""조인 키가 요구하는 «유일 색인» — 이름 · DDL · 식 · 카탈로그 조회가 여기 «한 자리»에 산다.

🔴 [S-283 · 판정 440 ③㉠ · 442 ③] WHY IT MOVED. This cluster lived in
`virtual_join/config.py`, and the virtual join has since been removed — but the thing that
needs it did not go anywhere: `chain.synthesis.ensure_declared_unique_keys` builds the
UNIFIED join's `key.unique` index through these names. Deleting the package by name would
have taken the uniqueness of the join the owner migrated TO (S-248: a leftover `uq_vjoin_*`
refuses every insert on that table with 23505, and the group fails permanently on retry).
So the seat moved first and the package was deleted after.

🔴 `INDEX_PREFIX` IS A VALUE, NOT A NAME TO TIDY. The retraction population is defined BY
that prefix — 「접두로 고르는 것이 이 안전장치의 전부」. Rename it and every existing index
falls outside the product's reach; widen it and an operator's hand-built index falls inside.
It names a package that is gone, so it LOOKS wrong. Leave it wrong: the value is written
into live databases, and changing it is a migration and a separate round.

🔴 AND THE EXPRESSION COMES WITH THEM, WHICH IS THE POINT. `index_key_expression` is not
the index's private spelling — the index DDL, `join_onclause` and `crud`'s key comparison
all render a key through it, and PostgreSQL uses an expression index ONLY when the query's
expression matches it. Two spellings are not a type error; they are a sequential scan over
ten million rows with every test green. Keeping the definition single is what makes that
guarantee structural rather than a thing to remember.

⚰️ THE BACK-ALIAS IS GONE (step 4). `virtual_join.config` used to import these names back so
the old spellings kept working while the package was dismantled; the surviving half of that
module is `chain.legacy_join_declaration` and it imports them from here directly.
"""
import hashlib
import re


INDEX_PREFIX = "uq_vjoin_"

_MAX_IDENTIFIER = 63

def _folds_list(columns: list, folds) -> list:
    """`folds`를 `columns`와 같은 길이의 목록으로 정규화한다(항목: 규칙 dict 또는 None)."""
    if not folds:
        return [None] * len(columns)
    return [folds[i] if i < len(folds) else None for i in range(len(columns))]

def required_index_name(table: str, columns: list, folds=None) -> str:
    """조인 키를 덮는 UNIQUE 인덱스의 권장 이름(63바이트 이내).

    표기 정규화가 걸린 조인 키는 **다른 인덱스**를 요구한다(컬럼이 아니라 접힌 식에 대한
    유일성). 이름이 같으면 운영자가 평범한 인덱스를 이미 만들어 둔 자리에서 이름 충돌만
    보고 「이미 있다」고 읽으므로, 접히는 키에는 `_nf` 접미를 붙여 **다른 이름**을 준다.
    """
    # 🔴 THE NAME CARRIES THE SHAPE, so the old index and the new one can COEXIST while a
    # deployment migrates (S-181). Without `_ns` the null-safe index would be asked for
    # under the name a plain `UNIQUE (a, b)` already holds, and `CREATE` would fail with
    # 「already exists」 — leaving the operator to drop an index blind, on a live table,
    # to find out whether the new one even builds.
    suffix = ("_nf" if any(_folds_list(columns, folds)) else "") + "_ns"
    base = "%s%s_%s%s" % (INDEX_PREFIX, table, "_".join(columns), suffix)
    if len(base.encode("utf-8")) <= _MAX_IDENTIFIER:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    keep = _MAX_IDENTIFIER - len(INDEX_PREFIX) - len(digest) - 1
    return "%s%s_%s" % (INDEX_PREFIX,
                        ("%s_%s%s" % (table, "_".join(columns), suffix))[:keep], digest)

def column_is_text(table: str, column: str) -> bool:
    """Is `table.column` a text column? Unknown answers 「yes」 (S-245).

    ⚠️ UNKNOWN MEANS 「THE OLD EXPRESSION」, WHICH IS THE SAFE DIRECTION. Saying
    「not text」 for a column we cannot resolve would put `::text` into an index expression
    that existing indexes do not have, and every join on that table would go unapproved -
    an outage. Saying 「text」 leaves a numeric key at that seat exactly as broken as it was
    before this round, which is the status quo and is loud rather than silent.
    """
    try:
        from database import models
        import notation_norm

        model = models.DYNAMIC_TABLES.get(table) if table else None
        attribute = getattr(model, str(column), None) if model is not None else None
        if attribute is None:
            return True
        return notation_norm.is_text_type(getattr(attribute, "type", None))
    except Exception:                                              # noqa: BLE001
        return True

def index_key_expression(column: str, fold_rules=None, table: str = None) -> str:
    """인덱스 키 1개의 SQL 식 ― 평범한 컬럼이거나, **접힌 식**이거나.

    🔴 접힌 식은 `notation_norm.fold_sql_text` **하나에서만** 나온다. 조회 시점 식
    (`fold_notation_sql`)과 이 DDL이 같은 함수에서 나오지 않으면 PostgreSQL이 인덱스를
    **쓰지 않는다** ― 함수 인덱스는 질의 식이 인덱스 식과 일치할 때만 쓰이므로, 두 철자는
    이론적 불일치가 아니라 1,000만 행 순차 스캔이 되고 테스트는 전부 통과한다.
    """
    import notation_norm
    # 🔴 [S-245] THE EXPRESSION ITSELF IS SPELLED IN ONE PLACE - `notation_norm`. This
    # function decides ONE thing the other renderings cannot: whether the column is text,
    # which only a caller holding the TABLE can answer. Everything below is why the
    # expression has the shape it has, and it now describes what that pair builds.
    #
    # 🔴 NULL MUST EQUAL NULL HERE, AND THE INDEX IS HALF OF THAT (S-181, 판정 285·287).
    # A plain UNIQUE index calls two NULLs DISTINCT, so the uniqueness a virtual join is
    # approved against was not being enforced for a NULL key at all — measured on this
    # box: two `('L1', NULL)` rows both landed under `UNIQUE (a, b)`.
    #
    # ⛔ `NULLS NOT DISTINCT` IS NOT ACCEPTED, although PG15+ offers it. It fixes NULL and
    # leaves `''` a separate key, which contradicts 판정 284 (a blank IS null) — measured:
    # a second `('L1','')` is refused under it. `coalesce` satisfies BOTH rulings and works
    # on every version, so it is the ONE required shape.
    #
    # ⚠️ NO `btrim`, for `blank_sql_condition`'s reason: storage is canonical
    # (`normalize_stored_text`), so a whitespace-only value never reaches the database, and
    # an incomplete imitation of `str.strip()` here would be invalidated by the next schema
    # change. And this function is the ONE spelling: `join_onclause` builds the same
    # expression, because a query whose expression differs from the index's silently stops
    # using the index rather than failing.
    return notation_norm.key_expression_text(
        '"%s"' % column, fold_rules, text_column=column_is_text(table, column))

def required_index_ddl(table: str, columns: list, folds=None) -> str:
    """운영자가 그대로 실행할 수 있는 DDL 한 줄.

    `CONCURRENTLY`인 이유: 운영 테이블에 쓰기를 잠그지 않기 위해서다. 대가는 이 문장이
    트랜잭션 블록 안에서 돌 수 없다는 것이고(psql에서 손으로 실행하는 형태라 문제가 아니다),
    **취소되면 INVALID 인덱스가 남는다**는 것이다 ― 그래서 `unique_index_covering`이
    `indisvalid`를 검사한다. 취소했으면 지우고 다시 만들어야 판정이 인정한다.

    🔴 조인 키에 표기 정규화가 걸려 있으면 이것은 **함수 인덱스**가 된다. 평범한 b-tree
    인덱스로는 안 되는 이유가 두 가지이고 **둘 다 치명적**이다:
      ① 접힌 비교는 그 인덱스를 못 쓴다(순차 스캔).
      ② 애초에 게이트가 묻는 유일성을 **보장하지 않는다** ― 원본으로 서로 다른 두 행
         ('CL-1'과 'CL_1')이 접히면 한 값이 되므로, 컬럼에 UNIQUE가 있어도 접힌 키로는
         중복이다. 그 중복이 곧 조인 팬아웃이다.
    문장이 길어지는 것은 대가다. `\\uXXXX` 이스케이프라 전부 ASCII이고 psql에 그대로
    붙여 넣을 수 있다(제어문자를 날것으로 싣지 않는 이유가 그것이다).
    """
    fl = _folds_list(columns, folds)
    return 'CREATE UNIQUE INDEX CONCURRENTLY %s ON "%s" (%s);' % (
        required_index_name(table, columns, folds), table,
        ", ".join(index_key_expression(c, f, table) for c, f in zip(columns, fl)))

def _dialect_of(db) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""

_INDEX_EXPR_CASTS = ("::text", "::character varying", "::varchar", "::bpchar",
                     "::character", "::name")

_REDUNDANT_PARENS_RE = re.compile(r"\(([A-Za-z_][A-Za-z0-9_]*)\)")

def _casefold_outside_literals(expr: str) -> str:
    """Lowercase everything except what sits inside single quotes.

    `''` inside a literal is SQL's escaped quote and closes nothing, which is why this
    walks rather than splitting: a naive `split("'")` would treat the escape as a
    delimiter and start lowercasing the literal's own text.
    """
    out, inside, index = [], False, 0
    while index < len(expr):
        char = expr[index]
        if char == "'":
            if inside and expr[index:index + 2] == "''":
                out.append("''")
                index += 2
                continue
            inside = not inside
            out.append(char)
        else:
            out.append(char if inside else char.lower())
        index += 1
    return "".join(out)

def normalize_index_expression(expr: str) -> str:
    """인덱스 키 식 1개를 **비교 가능한 형태**로 접는다. 순수 함수 ― 테스트가 직접 채점한다.

    [왜 텍스트 비교인가]
    PostgreSQL은 함수 인덱스의 식을 파스 트리로 들고 있고, 「내 식이 이 인덱스의 식과
    같은가」를 물어볼 카탈로그 API가 없다. 있는 것은 `pg_get_indexdef(oid, 열번호, true)`
    ― PG 자신의 렌더링 ― 뿐이라, 우리 식을 같은 규약으로 접어 맞춘다.

    지우는 것은 **PG가 덧붙이는 것들뿐**이다:
      · 식별자 따옴표 ("core_lot" → core_lot)
      · 캐스트 접미 (varchar 컬럼을 text 인자에 넘길 때 PG가 (col)::text로 렌더한다)
      · 벌거벗은 식별자를 감싼 잉여 괄호 ((core_lot) → core_lot)
      · 공백 (우리 리터럴에는 공백이 없다 ― `\\uXXXX` 이스케이프와 알파벳뿐이라
        전부 지워도 리터럴 안을 건드리지 않는다. `notation_norm._check_pattern_shape`가
        그 전제를 import 시점에 단언한다.)

    🔴 지우지 **않는** 것: `COLLATE`. 다른 콜레이션으로 만든 인덱스는 같은 식이 아니고,
    PostgreSQL이 기본 콜레이션 비교에 그것을 쓴다는 보장도 없다. 모르면 거부다.
    """
    # 🔴 FUNCTION NAMES ARE CASE-INSENSITIVE IN SQL AND STRING LITERALS ARE NOT (S-181).
    # We build `coalesce(...)`; PostgreSQL renders it `COALESCE(...)`. Measured: the two
    # normalised to different strings, so a correctly-built index was not recognised and
    # every virtual join went unapproved. Folding case OUTSIDE quoted literals is the one
    # rule that makes the comparison mean what it says — folding the whole string would
    # change `'A'` into `'a'` and quietly accept an index built on a different value.
    out = _casefold_outside_literals(expr or "")
    out = out.strip()
    if out.startswith("(") and out.endswith(")"):
        # 한 겹 벗겨서 괄호가 균형을 유지하면 잉여 괄호였다.
        inner = out[1:-1]
        if inner.count("(") == inner.count(")"):
            out = inner
    out = out.replace('"', "")
    for cast in _INDEX_EXPR_CASTS:
        out = out.replace(cast, "")
    out = re.sub(r"\s+", "", out)
    prev = None
    while prev != out:                  # (a) 안에 (b)가 또 있을 수 있다
        prev = out
        out = _REDUNDANT_PARENS_RE.sub(r"\1", out)
    return out

def _index_key_expressions(db, indexrelid, nkeys: int) -> list:
    """인덱스의 키 열들을 PG 자신의 렌더링으로. 평범한 컬럼이면 컬럼 이름이 그대로 나온다."""
    from sqlalchemy import text
    out = []
    for i in range(1, nkeys + 1):
        out.append(db.execute(text("SELECT pg_get_indexdef(:oid, :i, true)"),
                              {"oid": indexrelid, "i": i}).scalar())
    return out

def unique_index_covering(db, table: str, columns: list, folds=None):
    """조인 키를 덮는 **UNIQUE 인덱스**의 이름. 없으면 None.

    부분집합이면 충분하다: `(a)`에 UNIQUE가 있으면 `(a,b)`로도 당연히 유일하다.

    행을 세지 않는다 ― 카탈로그만 읽는다. 그래서 1,000만 행 테이블에서도 비용이
    테이블 크기와 무관하고, 답이 스냅샷이 아니라 **제약의 존재**다.

    [🔴 접히는 키는 **함수 인덱스**를 요구한다 ― 게이트가 폴드와 함께 움직이는 이유]
    표기 정규화가 걸린 조인 키에서 평범한 UNIQUE 인덱스는 이 게이트가 묻는 질문에 답하지
    않는다. 원본으로 서로 다른 두 행('CL-1', 'CL_1')이 접히면 한 값이 되므로, 컬럼 유일성이
    있어도 **접힌 키로는 중복**이고 그 중복이 정확히 조인 팬아웃이다. 그래서 접히는 키에는
    `indexprs IS NOT NULL`인 인덱스만 후보가 되고, 그 식이 우리 식과 일치해야 한다.
    이 방향의 오판(맞는 인덱스를 못 알아봐 거부)은 운영자에게 DDL을 한 번 더 보여 줄 뿐이고,
    반대 방향의 오판(틀린 인덱스를 통과)은 게이트가 없는 것과 같다.

    배제 셋의 이유는 모듈 상단에 있다. `indexprs`만 **접히는 키에서 배제에서 풀린다** ―
    그때는 컬럼이 아니라 식에 대한 유일성이 바로 우리가 원하는 것이기 때문이다.
    `indpred`(부분 인덱스)와 `indisvalid`는 그대로 배제다.

    PostgreSQL이 아니면 **None을 돌려준다**(모른다). 안전한 방향의 무지다 ― 모르면 거부다.
    """
    from sqlalchemy import text
    if not columns:
        return None
    if _dialect_of(db) != "postgresql":
        return None
    fl = _folds_list(columns, folds)

    # ⚰️ THE PLAIN-COLUMN BRANCH IS GONE (S-181, 판정 287). It looked for a
    # `UNIQUE (a, b)` index, and that index calls two NULLs DISTINCT — so the uniqueness a
    # virtual join is approved against was never enforced for a NULL key. Measured on this
    # box: two `('L1', NULL)` rows both landed under it. Every join key is now an
    # EXPRESSION key (`coalesce(col, '')`), so there is one candidate shape and one branch.
    #
    # ⚠️ A DEPLOYMENT THAT HAS NOT MIGRATED LOSES ITS JOINS UNTIL IT DOES, and that is the
    # intended direction: a join running on an index that does not enforce its uniqueness
    # is a join returning answers nobody has checked. `migrations/add_vjoin_null_safe_indexes.py`
    # is the pair, and it counts the existing duplicate keys BEFORE it offers to build.
    # 접히는 키 ― **식 인덱스만** 후보다.
    rows = db.execute(text("""
        SELECT i.relname AS idx, x.indexrelid AS oid, x.indnkeyatts AS nkeys
        FROM pg_index x
        JOIN pg_class c ON c.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = :t AND n.nspname = 'public'
          AND x.indisunique AND x.indisvalid
          AND x.indpred IS NULL AND x.indexprs IS NOT NULL
    """), {"t": table}).fetchall()
    wanted = {normalize_index_expression(index_key_expression(c, f, table))
              for c, f in zip(columns, fl)}
    for idx, oid, nkeys in rows:
        keys = {normalize_index_expression(e)
                for e in _index_key_expressions(db, oid, nkeys)}
        if keys <= wanted:
            return idx
    return None
