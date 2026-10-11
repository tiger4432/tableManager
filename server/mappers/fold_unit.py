# -*- coding: utf-8 -*-
"""총괄 402f1ab2e — 접기 맵퍼 (소유자 「충돌은 replace map 느낌으로 dt_wafer_id 단위로」 · 「AUTO 잡 먼저, 그 안에서 시간
빠른 거」 · 「매뉴얼끼리도 같은 규칙」).

A unit table holds one row per unit (a job on a wafer). Per group (`group`) one unit wins: the one whose
`prefer_column` holds `prefer_text` (any case), then the earliest `order` (a blank last), then the smaller row_id -
`replay._ranked_duplicates`, the row fold's own ranking. A losing unit's log rows (`match`: log column = unit column)
are marked «folded into <winning unit>», each mark carrying its unit row as `origin_row_id`. The winner's rows are not
written (총괄 10-11 - the row fold marks the same column inside the kept job): a unit that loses and later wins keeps
its old mark until withdrawn (RUN.md).

Two rules call it with the same params: on the unit table, and on the log table (`unit_table` named) - a new log row
re-decides its group too. A deleted unit row takes back its marks but does not re-decide its group: replay the unit
table's rule.
"""
from __future__ import annotations

NAME = "fold_by_unit"
#: what each argument must be - a list written as text was read a letter at a time (총괄 67dffd619)
PARAMS = {"unit_table": str, "group": str, "unit": str, "order": str, "prefer_column": str, "prefer_text": str,
          "match": list, "mark_column": str}
FOLDED_INTO = "folded into %s"
CHUNK = 1000


def fold_by_unit(db, payloads, rule=None):
    from sqlalchemy import String, cast, select, tuple_

    from chain import replay
    from database import models
    from mapper_sdk import payloads_to_df

    df = payloads_to_df(payloads)
    if df.empty:
        return {"updates": []}
    params = rule["params"]
    units, logs = models.DYNAMIC_TABLES[params["unit_table"]], models.DYNAMIC_TABLES[rule["target_table"]]
    pairs = [(m["left"], m["right"]) for m in params["match"]]
    group = cast(getattr(units, params["group"]), String)
    ids = [str(r) for r in df["row_id"]]

    def chunks(items):
        items = list(items)
        return (items[i:i + CHUNK] for i in range(0, len(items), CHUNK))

    groups = set()
    if rule.get("trigger_table") == params["unit_table"]:
        for part in chunks(ids):
            groups.update(g for (g,) in db.query(group).filter(units.row_id.in_(part)))
    else:
        keys = set()
        for part in chunks(ids):
            keys.update(tuple(r) for r in db.query(*[getattr(logs, left) for left, _r in pairs])
                        .filter(logs.row_id.in_(part)))
        unit_key = tuple_(*[getattr(units, right) for _l, right in pairs])
        for part in chunks(keys):
            groups.update(g for (g,) in db.query(group).filter(unit_key.in_(part)))
    groups.discard(None)
    if not groups:
        return {"updates": []}

    prefer = ((params["prefer_column"], params["prefer_text"])
              if params.get("prefer_column") and params.get("prefer_text") else None)
    kept = {}
    for part in chunks(sorted(groups)):
        ranked = replay._ranked_duplicates(units, [params["group"]], params["order"], "min", prefer,
                                           among=[group.in_(part)])
        kept.update({row_id: winner for row_id, winner in db.execute(select(ranked.c.row_id, ranked.c.kept))})
    unit_of, name_of = {}, {}
    for part in chunks(kept):
        for row in db.query(units.row_id, getattr(units, params["unit"]),
                            *[getattr(units, right) for _l, right in pairs]).filter(units.row_id.in_(part)):
            name_of[row[0]] = row[1]
            unit_of.setdefault(tuple(row[2:]), row[0])
    log_key = tuple_(*[getattr(logs, left) for left, _r in pairs])
    updates = []
    for part in chunks(unit_of):
        for row in db.query(logs.row_id, *[getattr(logs, left) for left, _r in pairs]).filter(log_key.in_(part)):
            unit = unit_of[tuple(row[1:])]
            winner = kept[unit]
            if unit != winner:      # the winner's rows are not written (총괄 10-11: the row fold marks them too)
                updates.append({"row_id": row[0], "origin_row_id": unit,
                                "updates": {params["mark_column"]: FOLDED_INTO % name_of[winner]}})
    return {"updates": updates}


def _register():
    import mapper_sdk
    mapper_sdk.register(NAME, fold_by_unit, params=PARAMS, facts={
        "columns": lambda rule: [((rule or {}).get("params") or {}).get("mark_column")], "stamps_origin": lambda rule: True})


_register()
