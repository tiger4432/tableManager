# -*- coding: utf-8 -*-
"""S-181. Build the null-safe unique indexes every virtual join now requires.

🔴 WHY THE SHAPE CHANGED (판정 285·287). A virtual join is approved only against a UNIQUE
index covering its right-side key — and a plain `UNIQUE (a, b)` calls two NULLs DISTINCT.
Measured on this box: two `('L1', NULL)` rows both landed under one. So the uniqueness the
join was approved against was never enforced for a NULL key, and the join meanwhile matched
no row at all for such a key, because SQL's `=` does not match NULL to NULL.

Both halves are now `coalesce(<col>, '')`: the join compares that way and the index is built
that way. `NULLS NOT DISTINCT` is deliberately NOT accepted — it fixes NULL and leaves `''`
a separate key, which contradicts 판정 284 (a blank IS null), and it needs PG15+.

⛔ IT COUNTS BEFORE IT OFFERS. A plain index let duplicate NULL keys accumulate, so the new
index may be UNBUILDABLE on live data — and the number of offending rows is the first thing
an operator needs, not a failed `CREATE` twenty minutes in. The dry run reports it per rule
and names sample keys; nothing is created until `--apply`.

⚠️ DRY RUN IS THE DEFAULT, and `CREATE INDEX CONCURRENTLY` cannot run inside a transaction
block, so the build uses its own AUTOCOMMIT connection outside the application pool — the
S-167 lesson, same as `tune_layer_tables`.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text                                          # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def _rules(db):
    import virtual_join_config as vjc
    from database import crud

    return vjc.load_virtual_join_rules(known_tables=crud.TABLE_CONFIG) or []


def _duplicate_census(db, table, columns, folds):
    """How many key values already appear twice under the NEW rule, and a few of them.

    🔴 THIS IS THE NUMBER THE OPERATOR NEEDS FIRST. Under the old index these rows were
    legal; under the new one they are a unique violation, so a `CREATE` that has not been
    preceded by this count is a `CREATE` that fails on live data for a reason nobody was
    shown.
    """
    import virtual_join_config as vjc

    keys = ", ".join(vjc.index_key_expression(c, f) for c, f in zip(columns, folds))
    rows = db.execute(text(f"""
        SELECT {keys}, count(*) AS n
          FROM "{table}"
         GROUP BY {keys}
        HAVING count(*) > 1
         ORDER BY count(*) DESC
         LIMIT 5
    """)).fetchall()
    total = db.execute(text(f"""
        SELECT count(*) FROM (
            SELECT 1 FROM "{table}" GROUP BY {keys} HAVING count(*) > 1
        ) AS d
    """)).scalar()
    return total or 0, [tuple(r) for r in rows]


def _existing(db, name):
    return db.execute(text(
        "SELECT 1 FROM pg_class WHERE relname = :n AND relkind = 'i'"),
        {"n": name}).scalar() is not None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="실제로 인덱스를 만듭니다 (기본은 보여 주기만 합니다)")
    parser.add_argument("--rule", action="append", dest="rules", metavar="NAME",
                        help="이 규칙만 (여러 번 지정 가능)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    import virtual_join_config as vjc
    from database.database import SessionLocal

    db = SessionLocal()
    plan, blocked = [], []
    try:
        if db.get_bind().dialect.name != "postgresql":
            print("이 스크립트는 PostgreSQL 전용입니다.", file=sys.stderr)
            return 2
        for rule in _rules(db):
            if args.rules and rule.get("name") not in args.rules:
                continue
            table = rule.get("right_table")
            columns = list(rule.get("right_columns") or [])
            folds = vjc._folds_list(columns, rule.get("right_folds") or [])
            if not (table and columns):
                continue
            name = vjc.required_index_name(table, columns, rule.get("right_folds"))
            ddl = vjc.required_index_ddl(table, columns, rule.get("right_folds"))
            print(f"\n== {rule.get('name')} == {table}({', '.join(columns)})")
            if _existing(db, name):
                print(f"   이미 있음: {name}")
                continue
            duplicates, sample = _duplicate_census(db, table, columns, folds)
            if duplicates:
                # ⛔ NAMED, NOT SWALLOWED. The rows are data, and deciding which of two
                # rows sharing a key is the true one is not a migration's decision.
                print(f"   🔴 같은 키를 가진 값이 {duplicates}개 있습니다 — 이 인덱스는 "
                      f"지금 «만들어지지 않습니다».")
                for row in sample:
                    print(f"      {row[:-1]} × {row[-1]}")
                print("      먼저 데이터를 정리하세요. 어느 행이 참인지는 "
                      "스크립트가 고를 수 없습니다.")
                blocked.append(rule.get("name"))
                continue
            print(f"   {'RUN ' if args.apply else 'DRY '}{ddl}")
            plan.append((rule.get("name"), ddl))
    finally:
        db.close()

    if not args.apply:
        print(f"\n(아무것도 만들지 않았습니다. {len(plan)}개를 만들려면 --apply. "
              f"막힌 규칙 {len(blocked)}개{': ' + ', '.join(blocked) if blocked else ''})")
        return 0

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from database.database import SQLALCHEMY_DATABASE_URL

    # CONCURRENTLY cannot run inside a transaction block, and a pooled connection switched
    # to AUTOCOMMIT poisons the next checkout (S-167). Own engine, disposed here.
    engine = create_engine(SQLALCHEMY_DATABASE_URL, poolclass=NullPool,
                           isolation_level="AUTOCOMMIT",
                           connect_args={"application_name": "assy_vjoin_null_safe"})
    try:
        with engine.connect() as conn:
            for name, ddl in plan:
                print(f"\n-- {name} --\nRUN {ddl}")
                conn.execute(text(ddl))
    finally:
        engine.dispose()
    print(f"\n{len(plan)}개 인덱스를 만들었습니다. "
          f"막힌 규칙 {len(blocked)}개는 데이터 정리 뒤 다시 돌리세요.")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
