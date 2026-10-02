# -*- coding: utf-8 -*-
"""표 하나를 «비운다» — 행 · 그 표의 칸 층 · 덮어쓰기, 그리고 그 표를 읽는 원장 원자 (총괄 35b76ba92).

    python server/scripts/empty_table.py <표>                                # 보고만(기본). 아무것도 안 쓴다
    python server/scripts/empty_table.py <표> --apply --confirm-rows <보고의 행 수> [--by <이름>]

`--apply` 는 보고가 보인 행 수를 다시 받아야 돈다 — 그 사이 표가 움직였으면 거절한다.
한 트랜잭션: 표의 행 · 그 표의 cell_sources · cell_overwrites 를 지우고 감사 로그에 요약 한 줄.
그 뒤 그 표를 읽는 원장 소스마다 `backfill.rescope(whole_source, apply)` — 표가 잃은 행의 원자를
거둔다. 아웃박스 이벤트는 내지 않는다(SQL 로 지운다) — 체인 규칙은 아무것도 깨지 않는다.

⚠️ 행 하나씩 지우는 정본 문(`crud.delete_rows_batch`)은 1만 행당 ~2.5 s 라 100만 행에 안 맞는다.
   이 문은 «표 통째»만 한다.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # S-159: cp949 콘솔에서 한 글자에 죽지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass

#: 감사 로그 요약 줄의 출처 이름.
SOURCE = "empty_table"


class Refused(ValueError):
    """비우지 않는다 — 이유를 이름 대어."""


def report(db, setup, table, rules) -> dict:
    """지우면 무엇이 가나. 읽기만 한다."""
    from sqlalchemy import text
    from chain.ingestion_worker import watches_table
    from database import crud, models
    from ledger import followup, schema

    try:
        crud.refuse_write_to_view(table)
    except crud.ReadOnlyRelation as exc:
        raise Refused(str(exc)) from exc
    if table not in models.DYNAMIC_TABLES:
        raise Refused("'%s' 는 선언된 표가 아닙니다 (table_config)" % table)
    layers = dict(db.execute(text(
        "SELECT source_name, count(*) FROM cell_sources WHERE table_name = :t GROUP BY source_name"),
        {"t": table}).fetchall())
    atoms = {}
    for source in followup.sources_for_table(setup, table):
        atoms[source] = db.execute(text(
            "SELECT count(*) FROM %s WHERE source_who = :s" % schema.LEDGER_TABLE),
            {"s": source}).scalar()
    return {
        "table": table,
        "rows": db.execute(text('SELECT count(*) FROM "%s"' % table)).scalar(),
        "layers": sum(layers.values()),
        "user_layers": sum(n for name, n in layers.items()
                           if crud.layer_writer(name) == crud.USER_SOURCE),
        "overwrites": db.execute(text(
            "SELECT count(*) FROM cell_overwrites WHERE table_name = :t"), {"t": table}).scalar(),
        "ledger_atoms": atoms,
        "chain_rules": sorted(rule["name"] for rule in rules if watches_table(rule, table)),
    }


def empty(db, engine, setup, table, rules, confirm_rows, by) -> dict:
    """비운다. `confirm_rows` 가 지금의 행 수와 다르면 아무것도 안 하고 거절."""
    from sqlalchemy import text
    from database import crud
    from ledger import backfill

    before = report(db, setup, table, rules)
    if int(confirm_rows) != before["rows"]:
        raise Refused("'%s' 는 지금 %d 행입니다, %s 가 아니라 — 보고를 다시 보고 그 수로"
                      % (table, before["rows"], confirm_rows))
    tx = "%s_%s" % (SOURCE, uuid.uuid4().hex[:8])
    done = {"rows": db.execute(text('DELETE FROM "%s"' % table)).rowcount,
            "layers": db.execute(text("DELETE FROM cell_sources WHERE table_name = :t"),
                                 {"t": table}).rowcount,
            "overwrites": db.execute(text("DELETE FROM cell_overwrites WHERE table_name = :t"),
                                     {"t": table}).rowcount}
    crud.create_audit_log(db, table, "*", "*", before["rows"], 0, SOURCE, by, transaction_id=tx)
    db.commit()
    done["ledger_withdrawn"] = {
        source: backfill.rescope(engine, setup, source, None, (), apply=True,
                                 whole_source=True).get("gone_withdrawn", 0)
        for source in before["ledger_atoms"]}
    return {"before": before, "done": done, "transaction_id": tx}


def render_report(found) -> str:
    lines = ["표 %s — 행 %d · 칸 층 %d (그중 사람 층 %d — 비우면 사람이 고친 값도 같이 갑니다) · 덮어쓰기 %d"
             % (found["table"], found["rows"], found["layers"], found["user_layers"],
                found["overwrites"])]
    for source, n in sorted(found["ledger_atoms"].items()):
        lines.append("  원장 소스 %s — 원자 %d (비운 뒤 거둡니다)" % (source, n))
    if not found["ledger_atoms"]:
        lines.append("  이 표를 읽는 원장 소스: 없음")
    lines.append("  이 표를 트리거로 읽는 체인 규칙: %s (비우기는 아무 규칙도 깨우지 않습니다)"
                 % (", ".join(found["chain_rules"]) or "없음"))
    lines.append("→ 다음: --apply --confirm-rows %d" % found["rows"])
    return "\n".join(lines)


def render_done(result) -> str:
    done = result["done"]
    lines = ["비움 %s — 행 %d · 칸 층 %d · 덮어쓰기 %d (감사 로그 요약 한 줄, 트랜잭션 %s)"
             % (result["before"]["table"], done["rows"], done["layers"], done["overwrites"],
                result["transaction_id"])]
    for source, n in sorted(done["ledger_withdrawn"].items()):
        lines.append("  원장 소스 %s — 원자 %d 거둠" % (source, n))
    lines.append("  아웃박스 이벤트 0 — 체인 규칙은 이 비우기로 깨지 않았습니다")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="표 하나를 비운다 (보고 -> --apply --confirm-rows)")
    parser.add_argument("table")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-rows", type=int, default=None)
    parser.add_argument("--by", default="operator")
    args = parser.parse_args(argv)
    if args.apply and args.confirm_rows is None:
        print("거절: --apply 는 --confirm-rows <보고의 행 수> 와 같이 — 먼저 --apply 없이 보고를 보세요")
        return 2

    from chain.ingestion_worker import loaded_chain_rules
    from database.database import SessionLocal, engine
    from ledger.setup import load_setup

    db = SessionLocal()
    try:
        setup, rules = load_setup(), loaded_chain_rules()
        if args.apply:
            print(render_done(empty(db, engine, setup, args.table, rules, args.confirm_rows, args.by)))
        else:
            print(render_report(report(db, setup, args.table, rules)))
    except Refused as exc:
        print("거절: %s" % exc)
        return 2
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
