"""선언이 `cardinality: one` 이라 말하면 «제품이» 그 유일성을 세운다 (S-235).

> 소유자 2026-09-14: 「유니크 키는 **기계가 알아서** 세팅하게 해. 절대 인간에게 복잡한 행위를
> 요구하지 말 것」 · 「키 중복되면 **접든가** 해」

[무엇을 대체하나] 오늘 제품은 유일 인덱스가 없으면 조인을 거절하고 운영자에게 **DDL 문구**를
내민다. 그러면 운영자가 할 일이 넷이다 — 거절을 찾고 · 중복을 직접 찾고 · 지울지 합칠지 정하고 ·
`CREATE UNIQUE INDEX` 를 손으로 돌린다. 완성의 정의(「두 줄 이내」)에 정면으로 걸리고,
2026-09-14 에 운영자가 «조인을 전부 끄는» 것으로 끝났다.

[이 모듈이 하는 것 — 순서가 곧 안전이다]
    ① 유효한 인덱스가 이미 있나            -> 있으면 아무것도 안 한다
    ② 취소된 빌드의 INVALID 잔해가 있나     -> 그것이 거절의 원인일 수 있다. 지우고 다시 만든다
    ③ 만들어 본다                         -> 되면 끝. 중복이 없다는 뜻이다
    ④ 중복이 막으면                       -> «값과 건수»로 보고한다. DDL 이 아니라 «사실»을 준다
🔴 ④ 가 이 모듈의 요점이다. 접는 것(행을 지우거나 합치는 것)은 «데이터 변경»이라 이 파일이
   혼자 정하지 않는다 — 무엇을 접을지 먼저 «말하고», 접기는 별도의 명시적 걸음이다.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("VirtualJoin.UniqueKey")

#: 보고에 싣는 중복 키의 최대 건수. 수만 건이면 목록이 진단이 아니라 소음이 된다.
MAX_REPORTED_DUPLICATES = 20


def _expressions(columns, folds):
    from virtual_join import config as vjc
    return [vjc.index_key_expression(column, (folds or [None] * len(columns))[index]
                                     if index < len(folds or []) else None)
            for index, column in enumerate(columns)]


def invalid_leftovers(db, table: str, columns: list, folds=None) -> list:
    """이 조인 키를 덮지만 «INVALID» 인 인덱스들의 이름.

    🔴 왜 따로 세나. `unique_index_covering` 은 `indisvalid` 를 «일부러» 뺀다 — 취소된
    CREATE INDEX CONCURRENTLY 의 잔해는 제약을 강제하지 않으므로 있으나 마나다. 그런데
    그 잔해가 «이름»을 붙잡고 있어서, `IF NOT EXISTS` 가 「이미 있다」로 답하고 아무 일도
    안 일어난다. 즉 중복이 하나도 없어도 조인이 영영 거절될 수 있다 — 이름이 막고 있어서.
    """
    from sqlalchemy import text as sa_text
    rows = db.execute(sa_text("""
        SELECT i.relname
          FROM pg_index x
          JOIN pg_class c ON c.oid = x.indrelid
          JOIN pg_class i ON i.oid = x.indexrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relname = :t AND n.nspname = 'public'
           AND x.indisunique AND NOT x.indisvalid
    """), {"t": table}).fetchall()
    return [row[0] for row in rows]


def duplicate_keys(db, table: str, columns: list, folds=None,
                   limit: int = MAX_REPORTED_DUPLICATES) -> list:
    """유일성을 막고 있는 «값»과 «건수». 운영자가 읽는 것은 이것이지 DDL 이 아니다."""
    from sqlalchemy import text as sa_text
    exprs = _expressions(columns, folds)
    select = ", ".join("%s AS k%d" % (expr, index) for index, expr in enumerate(exprs))
    group = ", ".join(exprs)
    rows = db.execute(sa_text(
        'SELECT %s, count(*) AS n FROM "%s" GROUP BY %s HAVING count(*) > 1 '
        'ORDER BY n DESC LIMIT :lim' % (select, table, group)), {"lim": limit}).fetchall()
    # 🔴 «비어 있는 키»는 중복이 아니라 «부재»다 (상설: 길이 0 인 문자열은 NULL 이다).
    #    섞어서 말하면 운영자가 「수십만 행이 중복」을 보고 «없는 중복»을 찾으러 간다 —
    #    해야 할 일은 「이 행들에 키가 없다」이고, 그것은 다른 문장이자 다른 수리다.
    #    ⚠️ 그리고 부재는 «접어서» 될 일이 아니다 — 접으면 키 없는 행 전부가 한 행이 된다.
    duplicates, blanks = [], []
    for row in rows:
        key = [row[index] for index in range(len(exprs))]
        bucket = blanks if all(_is_blank(value) for value in key) else duplicates
        bucket.append({"key": key, "rows": row[-1]})
    return duplicates, blanks


def _is_blank(value) -> bool:
    """None · 빈 문자열 · 공백만 — 상설이 셋을 «같은 부재»로 접는다."""
    return value is None or not str(value).strip()


def inspect(db, table: str, columns: list, folds=None) -> dict:
    """지금 상태 한 장 — 고치지 «않는다». 판정과 조치를 가르는 자리다."""
    from virtual_join import config as vjc
    existing = vjc.unique_index_covering(db, table, columns,
                                         **({"folds": folds} if folds and any(folds) else {}))
    if existing:
        return {"state": "ok", "index": existing, "invalid": [], "duplicates": []}
    invalid = invalid_leftovers(db, table, columns, folds)
    duplicates, blanks = duplicate_keys(db, table, columns, folds)
    state = "duplicates" if duplicates else ("invalid" if invalid else "missing")
    if not duplicates and blanks and not invalid:
        # 🔴 다른 상태다 — 「중복이라 못 세운다」와 「키가 없어서 못 세운다」는 수리가 다르다
        state = "blank_keys"
    return {"state": state, "index": None, "invalid": invalid,
            "duplicates": duplicates, "blank_keys": blanks}


def describe(table: str, columns: list, report: dict) -> str:
    """운영자가 읽는 한 문장. «다음에 무엇이 일어나는지»까지 말한다."""
    state = report.get("state")
    if state == "ok":
        return "유일 인덱스 있음: %s" % report.get("index")
    if state == "missing":
        return ("%s(%s) 를 덮는 유일 인덱스가 없습니다 - 중복은 «없으므로» 제품이 만듭니다"
                % (table, ", ".join(columns)))
    if state == "invalid":
        return ("%s(%s) 의 유일 인덱스가 «INVALID» 로 남아 있습니다(%s) - 취소된 빌드의 잔해라 "
                "제약을 강제하지 않으면서 이름만 붙잡고 있습니다. 지우고 다시 만듭니다"
                % (table, ", ".join(columns), ", ".join(report.get("invalid") or ())))
    if state == "blank_keys":
        total = sum(entry["rows"] for entry in (report.get("blank_keys") or ()))
        return ("%s(%s) 의 %d 행에 그 키가 «비어 있습니다» - 중복이 아니라 «부재»입니다. "
                "채우거나, 카탈로그에서 그 컬럼의 null 정책을 정하십시오"
                % (table, ", ".join(columns), total))
    lines = ["%s(%s) 에 같은 조인 키를 가진 행이 있습니다 - 유일 인덱스를 세울 수 없습니다:"
             % (table, ", ".join(columns))]
    for entry in (report.get("duplicates") or [])[:MAX_REPORTED_DUPLICATES]:
        lines.append("   %s = %s -> %d 행"
                     % (", ".join(columns),
                        ", ".join(str(value) for value in entry["key"]), entry["rows"]))
    blanks = report.get("blank_keys") or []
    if blanks:
        # ⚠️ 둘이 같이 있을 수 있다. 그때 «본문»은 진짜 중복이고 빈 키는 꼬리표다 —
        #    순서를 바꾸면 고칠 것이 무엇인지가 뒤집힌다
        lines.append("   (그리고 키가 «비어 있는» 행 %d - 중복이 아니라 부재입니다)"
                     % sum(entry["rows"] for entry in blanks))
    return "\n".join(lines)


def ensure(db, table: str, columns: list, folds=None, apply: bool = True) -> dict:
    """상태를 보고, 세울 수 있으면 «세운다». 보고는 언제나 돌려준다.

    ⚠️ `CONCURRENTLY` 는 트랜잭션 «안»에서 못 돈다. 그래서 자동커밋 연결을 따로 연다 —
    세션의 트랜잭션에 얹으면 PostgreSQL 이 거절하고, 그 거절이 「인덱스를 못 만든다」로
    읽혀 원인이 데이터에 있는 것처럼 보인다.

    🔴 중복이 있으면 «아무것도 하지 않는다». 접는 것은 데이터 변경이고, 무엇을 접을지는
    이 함수가 혼자 정할 일이 아니다 — 보고에 값과 건수를 담아 돌려주는 것이 여기까지다.
    """
    report = inspect(db, table, columns, folds)
    report["created"] = None
    report["dropped"] = []

    if report["state"] == "ok" or report["state"] == "duplicates":
        return report
    if not apply:
        return report

    from virtual_join import config as vjc
    from sqlalchemy import text as sa_text

    engine = db.get_bind()
    try:
        connection = engine.execution_options(isolation_level="AUTOCOMMIT").connect()
    except Exception as open_error:
        report["error"] = "autocommit connection unavailable: %s" % open_error
        return report

    try:
        for name in report["invalid"]:
            # 잔해는 제약을 강제하지 않으면서 «이름»을 붙잡는다 — 지우는 것이 곧 고치는 것이다
            connection.execute(sa_text('DROP INDEX CONCURRENTLY IF EXISTS "%s"' % name))
            report["dropped"].append(name)
        ddl = vjc.required_index_ddl(table, columns,
                                     **({"folds": folds} if folds and any(folds) else {}))
        connection.execute(sa_text(ddl))
        report["created"] = ddl
        report["state"] = "ok"
    except Exception as create_error:
        # 여기서 실패하면 대개 «중복»이다. PostgreSQL 이 어떤 키인지까지 말해 주므로
        # 우리 진단으로 덮어쓰지 않고 그 문장을 그대로 나른다.
        report["error"] = str(create_error).strip().splitlines()[0]
        if not report.get("duplicates"):
            report["duplicates"], report["blank_keys"] = duplicate_keys(
                db, table, columns, folds)
        report["state"] = "duplicates" if report["duplicates"] else "failed"
    finally:
        try:
            connection.close()
        except Exception:
            pass
    return report


#: 프로세스당 규칙당 «한 번». 🔴 이것이 없으면 안 된다 — 이 판정이 사는 자리는 읽기 경로의
#: 5초 TTL 캐시라, 매 미스마다 DDL 을 던지게 된다. 2026-09-14 에 «같은 거절»이 5초마다
#: 로그를 채운 것이 바로 그 자리였고, 거기에 DDL 을 붙이면 로그가 아니라 데이터베이스를 채운다.
_TRIED = {}


def ensure_once(db, rule_name: str, table: str, columns: list, folds=None) -> dict:
    """이 프로세스에서 이 규칙에 대해 «처음일 때만» 세운다. 그 뒤엔 기억한 보고를 돌려준다."""
    if rule_name in _TRIED:
        return _TRIED[rule_name]
    switch = os.getenv("ASSY_VJOIN_AUTO_INDEX", "1").strip().lower()
    if switch in ("0", "false", "off", "no"):
        report = inspect(db, table, columns, folds)
        report["created"] = None
        report["dropped"] = []
        report["skipped"] = "ASSY_VJOIN_AUTO_INDEX=%s" % switch
    else:
        report = ensure(db, table, columns, folds, apply=True)
    _TRIED[rule_name] = report
    if report.get("created"):
        logger.warning("[VirtualJoin:%s] 유일 인덱스를 «제품이» 세웠습니다%s: %s",
                       rule_name,
                       (" (INVALID 잔해 %s 제거)" % ", ".join(report.get("dropped") or ())
                        if report.get("dropped") else ""),
                       report["created"])
    elif report.get("state") != "ok":
        logger.warning("[VirtualJoin:%s] %s", rule_name,
                       describe(table, columns, report))
    return report


def forget(rule_name: str = None):
    """선언이 바뀌면 다시 물어야 한다 — 기억은 «이 선언에 대한» 것이지 영구 판정이 아니다."""
    if rule_name is None:
        _TRIED.clear()
    else:
        _TRIED.pop(rule_name, None)

#: 접기 계획에 담는 키의 최대 수. 운영 표에서 중복이 수천이면 계획서가 진단이 아니라 덤프가 된다.
MAX_PLANNED_KEYS = 50


def fold_plan(db, table: str, columns: list, folds=None, limit: int = MAX_PLANNED_KEYS) -> dict:
    """접기 «전»에 무엇을 접을지 — 그리고 «접어도 되는지»를 가를 재료 (S-235, 판정 「접든가 해」).

    🔴 이 함수의 요점은 접는 것이 아니라 «두 경우를 가르는 것»이다:

        행들이 사실상 «같다»      -> 사본이다. 접어도 잃는 것이 없다
        행들이 «다르다»          -> 그 표의 신원은 이 컬럼이 아니다. 접으면 «데이터가 사라진다»
                                   고칠 것은 데이터가 아니라 «선언»이고, 그것이 S-226 의 교훈이다

    그래서 각 키마다 «어느 컬럼이 서로 다른가»를 같이 센다. 그 목록이 비어 있으면 접기는 안전하고,
    비어 있지 않으면 이 도구는 접자고 말하지 «않는다» — 사람이 볼 사실을 줄 뿐이다.

    ⛔ 아무것도 쓰지 않는다. 적용은 별도의 명시적 걸음이다.
    """
    from sqlalchemy import text as sa_text

    duplicates, blanks = duplicate_keys(db, table, columns, folds, limit=limit)
    exprs = _expressions(columns, folds)
    plans, unsafe = [], []

    for entry in duplicates:
        where = " AND ".join("%s = :v%d" % (expr, index)
                             for index, expr in enumerate(exprs))
        params = {"v%d" % index: str(value) for index, value in enumerate(entry["key"])}
        rows = db.execute(sa_text(
            'SELECT * FROM "%s" WHERE %s ORDER BY updated_at DESC NULLS LAST, row_id DESC'
            % (table, where)), params).mappings().fetchall()
        if len(rows) < 2:
            continue

        # 🔴 «메타 칸»은 비교에서 뺀다 — 그것들이 다른 것은 사본의 증거이지 차이의 증거가 아니다
        meta = {"row_id", "created_at", "updated_at", "business_key_val"}
        differing = sorted({
            column for column in rows[0].keys() if column not in meta
            and len({_comparable(row[column]) for row in rows}) > 1})

        plan = {"key": entry["key"], "rows": len(rows),
                "keep": rows[0].get("row_id"),
                "drop": [row.get("row_id") for row in rows[1:]],
                "differing_columns": differing}
        (unsafe if differing else plans).append(plan)

    return {"table": table, "columns": list(columns),
            "safe": plans, "unsafe": unsafe, "blank_keys": blanks}


def _comparable(value):
    """dict·list 는 해시가 안 되므로 비교 가능한 모양으로. «값이 같은가»만 물으면 된다."""
    if isinstance(value, (dict, list)):
        import json
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return value


def describe_fold_plan(plan: dict) -> str:
    """접기 계획을 사람이 읽는 문단으로. «안전한 것»과 «아닌 것»을 절대 같은 칸에 두지 않는다."""
    lines = []
    safe, unsafe = plan.get("safe") or [], plan.get("unsafe") or []
    if safe:
        lines.append("접어도 되는 키 %d - 메타 칸 말고는 값이 «같은» 행들입니다:" % len(safe))
        for entry in safe[:10]:
            lines.append("   %s -> %d 행 중 1 남김"
                         % (", ".join(str(v) for v in entry["key"]), entry["rows"]))
    if unsafe:
        lines.append("[!] 접으면 «데이터가 사라지는» 키 %d - 행들이 실제로 다릅니다:" % len(unsafe))
        for entry in unsafe[:10]:
            lines.append("   %s -> %d 행, 다른 컬럼: %s"
                         % (", ".join(str(v) for v in entry["key"]), entry["rows"],
                            ", ".join(entry["differing_columns"][:6])))
        lines.append("   [!] 이쪽은 «신원이 이 컬럼이 아니라는 뜻»입니다. 접지 말고 키를 넓히십시오")
    if plan.get("blank_keys"):
        total = sum(entry["rows"] for entry in plan["blank_keys"])
        lines.append("키가 «비어 있는» 행 %d - 중복이 아니라 부재입니다(접기 대상 아님)" % total)
    return "\n".join(lines) or "중복 없음"


def narrower_than_identity(table: str, columns: list, known_tables: dict = None):
    """조인이 «그 표의 신원보다 좁은» 키로 묻고 있으면, 그 신원을 돌려준다. 아니면 None.

    🔴 「행 하나는 사실 하나」(소유자 2026-09-15)의 «선언만으로 잡히는» 위반이다.
    카탈로그가 그 표의 신원을 이미 적어 두므로(`composite_key_source`), 조인 키가 그
    부분집합이면 **그 유일 인덱스는 영원히 설 수 없다** — 데이터를 한 행도 안 읽고 안다.

    ⚠️ 그리고 이 경우 «접기»는 답이 아니라 «파괴»다. 같은 키의 행들은 사본이 아니라 서로
    다른 사실이고(셀 좌표가 다르다), 접으면 그 사실들이 사라진다. 고칠 것은 데이터가 아니라
    조인이 선언한 «키»다.

    2026-09-14 에 운영자가 이 모양을 만나 «조인을 전부 껐다». 그날 필요했던 것은 중복 조회도
    DDL 도 아니고 이 한 줄이었다 — 「당신이 물은 키가 그 표의 신원보다 좁습니다」.
    """
    catalogue = (known_tables or {}).get(table) or {}
    identity = catalogue.get("composite_key_source")
    if not identity or not columns:
        return None
    asked, declared = set(columns), set(identity)
    # 부분집합이면서 «같지는 않은» 것 — 같으면 올바른 키다
    return list(identity) if asked < declared else None
